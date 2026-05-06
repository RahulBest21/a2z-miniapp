"""A2Z API Server — HTTP endpoints for Mini App ↔ Bot communication.

Runs alongside the Telegram bot (same asyncio loop) on a configurable port.
The mini app fetches these endpoints directly, solving the one-way sendData() problem.

Cloudflare Tunnel required for public HTTPS access from Telegram's webview:
  1. Install:  winget install cloudflare.cloudflared
  2. Login:    cloudflared tunnel login
  3. Create:   cloudflared tunnel create a2z-api
  4. Route:    cloudflared tunnel route dns a2z-api your-domain.com
  5. Run:      cloudflared tunnel run --url http://localhost:8765 a2z-api

Usage:
  from a2z_api import APIServer
  api = APIServer(port=8765)
  await api.start()   # runs alongside bot polling
"""

from aiohttp import web
import json
import logging

log = logging.getLogger("a2z.api")
_API_PORT = 8765
_API_BASE = "/api"


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


async def _verify_token(request: web.Request):
    """Extract and verify auth token from query param. Returns user_id or None."""
    token = request.query.get("token", "")
    if not token or len(token) < 8:
        return None
    # Defer import to avoid circular dependency
    from a2z_db import verify_auth_token, get_or_create_user
    user = verify_auth_token(token)
    if user:
        return user["telegram_id"]
    return None


# ═══════════════════════════════════════════════════════════════
# ROUTE HANDLERS
# ═══════════════════════════════════════════════════════════════

async def health(request: web.Request):
    return web.json_response({"ok": True, "service": "a2z-api"}, headers=_cors_headers())


async def get_state_api(request: web.Request):
    """Return full stored state JSON. Auth via ?token= param."""
    user_id = await _verify_token(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=403, headers=_cors_headers())

    from a2z_db import get_stored_state
    stored = get_stored_state(user_id)
    if not stored:
        return web.json_response({"error": "no_state"}, status=404, headers=_cors_headers())

    try:
        data = json.loads(stored)
    except Exception:
        data = {"raw": stored}

    return web.json_response(data, headers=_cors_headers())


async def get_leaderboard_api(request: web.Request):
    """Return leaderboard for a mock. Auth via ?token= &mock_id=."""
    user_id = await _verify_token(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=403, headers=_cors_headers())

    mock_id = request.query.get("mock_id", "")
    if not mock_id:
        return web.json_response({"error": "missing mock_id"}, status=400, headers=_cors_headers())

    from a2z_db import get_leaderboard, get_mock
    lb = get_leaderboard(mock_id, 20)
    mock = get_mock(mock_id)
    mock_title = mock["title"] if mock else mock_id
    lb_data = []
    for r in (lb or []):
        lb_data.append({
            "rank": r["rank"],
            "name": (r.get("first_name") or r.get("name", "?"))[:20],
            "score": r["score"],
            "total": r["correct"] + r["wrong"],
            "accuracy": round(r["accuracy"], 1),
            "user_id": r.get("user_id"),
        })
    result = {"mock_id": mock_id, "title": mock_title, "entries": lb_data}
    return web.json_response(result, headers=_cors_headers())


async def get_analytics_api(request: web.Request):
    """Return per-user analytics (subject/topic breakdown). Auth via ?token=."""
    user_id = await _verify_token(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=403, headers=_cors_headers())

    from a2z_db import get_user_stats, db_fetchall
    stats = get_user_stats(user_id) or {}
    # Get recent attempts
    attempts = db_fetchall(
        "SELECT a.*, m.title as mock_title FROM attempts a LEFT JOIN mocks m ON a.mock_id = m.mock_id WHERE a.user_id = ? ORDER BY a.submitted_at DESC LIMIT 10",
        (user_id,),
    )
    result = {
        "stats": stats,
        "recent_attempts": [dict(a) for a in (attempts or [])],
    }
    return web.json_response(result, headers=_cors_headers())


async def options_handler(request: web.Request):
    """CORS preflight."""
    return web.Response(status=200, headers=_cors_headers())


# ═══════════════════════════════════════════════════════════════
# SERVER
# ═══════════════════════════════════════════════════════════════

class APIServer:
    def __init__(self, port: int = _API_PORT, host: str = "0.0.0.0"):
        self.port = port
        self.host = host
        self._app = None
        self._runner = None
        self._site = None

    def _build_app(self):
        app = web.Application()
        app.router.add_get(f"{_API_BASE}/health", health)
        app.router.add_get(f"{_API_BASE}/state", get_state_api)
        app.router.add_get(f"{_API_BASE}/leaderboard", get_leaderboard_api)
        app.router.add_get(f"{_API_BASE}/analytics", get_analytics_api)
        app.router.add_route("OPTIONS", f"{_API_BASE}/{{tail:.*}}", options_handler)
        return app

    async def start(self):
        self._app = self._build_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        log.info("API server listening on http://%s:%d", self.host, self.port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            log.info("API server stopped")
