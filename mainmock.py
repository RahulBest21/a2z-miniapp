#!/usr/bin/env python3
"""
A2Z UPDATES ── Universal Mock Rebrander & AI Enhancer
═══════════════════════════════════════════════════════
Single‑file Telegram bot + CLI tool.

What it does
────────────
  1. Accepts ANY quiz mock .html file (any brand / template)
  2. Universally detects & replaces all branding → A2Z Updates
  3. Rephrases questions via Gemini (40‑key pool, rotating)
  4. Injects "Join A2Z Updates for more mocks" CTA into every explanation
  5. Returns the customised, ready‑to‑share mock

Setup
─────
  pip install python-telegram-bot google-generativeai
  python a2z_bot.py              # start the Telegram bot
  python a2z_bot.py file.html    # CLI – process one file
  python a2z_bot.py folder/      # CLI – process all .html in folder

Channel: https://t.me/A2Zupdates4U
"""

import asyncio, json, logging, os, random, re, sys, tempfile, time, traceback, hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════
try:
    from a2z_db import (
        init_db, db_execute, db_commit, db_fetchone, db_fetchall,
        get_or_create_user, add_admin, is_admin,
        register_mock, register_questions, get_mock, get_mock_questions, list_mocks,
        start_attempt, save_response, submit_attempt, get_attempt, get_user_attempts,
        get_leaderboard, get_user_rank, get_mock_stats, get_user_stats,
        create_invite, record_invite_join, get_monthly_invite_count,
        check_and_grant_access, has_free_access, use_free_mock, grant_free_access, grant_premium_access,
        verify_channel_membership, verify_referral_by_action, get_monthly_action_verified_count,
        register_editorial, list_editorials,
        store_state, get_stored_state,
        get_admin_overview, get_admin_users_list, get_admin_mocks_list,
        get_user_deep_stats, get_admin_invite_network, get_admin_all_user_ids,
        log_admin_action,
        get_taxonomy_tree, resolve_tags,
        update_user_stats_after_attempt, get_user_subject_summary,
        get_user_topic_breakdown, get_user_score_trend,
        get_user_weak_areas, get_user_silly_mistakes,
        create_challenge, accept_challenge, complete_challenge,
        create_trio, join_trio, check_trio_completion,
        close_db,
    )
    DB_OK = True
except ImportError:
    DB_OK = False
    log.warning("a2z_db not found — database features disabled")

try:
    from a2z_gamification import (
        apply_gamification_migration, award_xp, calculate_rank, xp_to_next_rank,
        apply_rank_decay, create_daily_quest, complete_daily_quest, get_today_quest,
        create_guild, join_guild, leave_guild, get_guild_info,
        create_raid, deal_raid_damage, get_active_raid,
        check_first_blood, get_fomo_message, hunter_license_html,
        RANK_NAMES, RANK_COLORS, RANK_THRESHOLDS,
        ACCESS_DAYS, INVITES_REQUIRED, INVITE_XP, QUIZ_XP, STREAK_XP, DECAY_XP, DECAY_DAYS,
    )
    GAME_OK = True
    from a2z_api import APIServer
    API_OK = True
except ImportError:
    GAME_OK = False
    API_OK = False
    log.warning("a2z_gamification or a2z_api not found — gamification/api disabled")

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s | %(levelname)-7s | %(message)s", level=logging.INFO)
log = logging.getLogger("a2z")

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════
CHANNEL_NAME = "Telegram Channel - A2Z Updates"
CHANNEL_LINK = "https://t.me/A2Zupdates4U"
CHANNEL_HANDLE = "@A2Zupdates4U"
CHANNEL_ID = os.environ.get("A2Z_CHANNEL_ID", "@A2Zupdates4U")  # for membership checks
CTA = "\n---\n📢 Join A2Z Updates for more mocks: https://t.me/A2Zupdates4U"

# ── Bot credentials (override via env vars) ──
BOT_TOKEN = os.environ.get("A2Z_BOT_TOKEN", "8781772186:AAExbgKmoPt1ILIyGfjScdmMqQOBxIMjR9k")

# ── 40 Gemini API keys (hardcoded pool) ──
GEMINI_KEYS = [
    "AIzaSyBFbY-3a4KPgvI9bsSfQ7urgG2hSv7HDM0",
    "AIzaSyDgeY0Uy-e-55TiBhLCRbgIzPJ9oGKgpl8",
    "AIzaSyC79QxcQBal_g9K3g7G0d6cy_VYJtmoArg",
    "AIzaSyCWZxS27wHPVeDrxHIl3Kwa7sxDUZ4bjmY",
    "AIzaSyBSJi9vU-S-FKnpx4PX7SUkLtyJT9UzyDI",
    "AIzaSyBJ6bj5--_tBO6fnGaIi9s6xrPp4OqLZ9Y",
    "AIzaSyAOqCOaj6hspmbrFm28eC45neC6LHFyqx0",
    "AIzaSyDuhVcT43sxynCqc0JcnOt8ghQ7iq5SbJo",
    "AIzaSyD3dNxlNRMizDxunTCOu3GkMR3ajq9dq28",
    "AIzaSyADxqrrSmShByiSXZYP6iJvzK2sosJhX5c",
    "AIzaSyCU6ag2TGqQ3NaLRWsqMaSLTa_jGsBv9fo",
    "AIzaSyBV50t36PQNqPBy7Vnv7FyfIZw_J1z41Ws",
    "AIzaSyC5b5EzbV3qMWT8RB7emxian1njyckvWbQ",
    "AIzaSyBe9M-KY8N2wJ8R0CspmHqWxrE0FV2FSnc",
    "AIzaSyAvwKpXEhX8ml670tj5XDDG75Aim6Socuw",
    "AIzaSyCXmNT_rlGaJ46w1Tqakbqi3rYcWnuyXXM",
    "AIzaSyB9sgjw-gI3eElIjN3Vs2iTSmhfF7w_wcE",
    "AIzaSyDAKk7b_iJVAsoQV4aNv5QAOicrW6bm2PU",
    "AIzaSyC2VN1nU4RTB6NGpUUoDvZ1BG36uAiXt0A",
    "AIzaSyCLS2s9u3PRfMT85Fl9oKIfHp2M4_QFgIo",
    "AIzaSyCc9eUkDKkjieboi2W-7xVXyiITKD_e0Qs",
    "AIzaSyCutj31DFdnrTAllubwlY2FdpNXZZrFqBQ",
    "AIzaSyDoju2sv99sFzOI6v0zfvC6kL0EyqE_MHo",
    "AIzaSyBnay1JboMO2faE5KEahRseEppxahvq0bE",
    "AIzaSyB5Kuvk0MZJspBlUb0valYCz1qiQy5dPzk",
    "AIzaSyBgAqEtMjKHCLHKLODQwhipyWn4l-poHJc",
    "AIzaSyDR80rYYnH6b30fS17tE-63_5vFcI6NF1w",
    "AIzaSyAHF3Sve3-vK2ecRX0SonUZdpWM5Vb3Jf8",
    "AIzaSyD5LyJEn6Qt0nQsCImAkyJnd8nCIuQLk20",
    "AIzaSyDsLEnLtkiQCXabNpUDhw7e6wXI0lpx7_k",
    "AIzaSyDsgeiIBlJT4CL6j9Bejcj9Wpx3S53dNxo",
    "AIzaSyB3JD-Aayqmd4m6FIdniOvqDEw9jt8yNFA",
    "AIzaSyAvTFb2E4TOlPTZjhKrUSNm4DW3ebtDN8M",
    "AIzaSyCykAV-jhIktKdhzq8TAgty6wXGAlECXsE",
    "AIzaSyDA2zNTjO3GHub2y44RfWe7a6JwwMJNSBc",
    "AIzaSyD_fE1Cua2oEL1Roi_M2AnUGxewkjO9XDA",
    "AIzaSyAhrQwyMlQYgPy89V4IQ0GCnPwcvz-9hHg",
    "AIzaSyDWEFPmdHzkqzEY3hbvfi27Hx8KWtTCKIQ",
    "AIzaSyCmGtxuzRPqXvkRwWgwemA9E1uCftcqxmk",
    "AIzaSyCocaQ_GkS1tEEpe7VwQo2u4qSuhhu7NaQ",
]

GEMINI_MODEL = "models/gemini-3.1-flash-lite-preview"

# Fallback chain — models tried in order if the primary fails
GEMINI_FALLBACK_MODELS = [
    "models/gemma-3-27b-it",
    "models/gemma-4-26b-a4b-it",
    "models/gemma-4-31b-it",
]

# ═══════════════════════════════════════════════════════════════════════════
# KEY MANAGER – Round‑Robin with cooldown (from your infrastructure)
# ═══════════════════════════════════════════════════════════════════════════
class KeyManager:
    def __init__(self, keys: List[str]):
        self.keys: List[Dict] = []
        for i, k in enumerate(keys):
            self.keys.append({
                "index": i + 1, "key": k, "status": "active",
                "cooldown_until": 0, "success_count": 0,
                "error_count": 0, "last_error": None, "dead": False,
            })
        self.current_index = 0

    def get_next_key(self) -> Optional[str]:
        if not self.keys:
            return None
        now = time.time()
        for _ in range(len(self.keys)):
            k_info = self.keys[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.keys)
            if k_info.get("dead"):
                continue
            if k_info["status"] == "cooling" and now >= k_info["cooldown_until"]:
                k_info["status"] = "active"
                log.info("🟢 Key #%d cooldown finished", k_info["index"])
            if k_info["status"] == "active":
                return k_info["key"]
        return None

    def mark_success(self, key: str):
        for k in self.keys:
            if k["key"] == key:
                k["success_count"] += 1
                return

    def mark_cooling(self, key: str, error_msg: str, duration: int = 60):
        for k in self.keys:
            if k["key"] == key:
                k["error_count"] += 1
                k["last_error"] = error_msg
                if "api_key_invalid" in error_msg.lower() or "400" in error_msg:
                    k["status"] = "dead"
                    k["dead"] = True
                    log.error("💀 Key #%d INVALID – marked dead", k["index"])
                else:
                    k["status"] = "cooling"
                    k["cooldown_until"] = time.time() + duration
                    log.warning("⚠️ Key #%d cooling %ds", k["index"], duration)
                return

# Singleton
key_manager = KeyManager(GEMINI_KEYS)


# ═══════════════════════════════════════════════════════════════════════════
# UNIVERSAL BRAND REPLACEMENT ENGINE
# ═══════════════════════════════════════════════════════════════════════════
_TME_LINK_RE = re.compile(r"https://t\.me/(\w+)")
_HANDLE_RE  = re.compile(r"(?<!\w)@(\w+)")
# CSS at‑rules and other non‑channel @words to NEVER replace
_HANDLE_BLACKLIST = {
    "media", "import", "font-face", "keyframes", "supports", "charset",
    "namespace", "page", "counter-style", "property", "layer", "container",
    "document", "color-profile", "font-feature-values", "font-palette-values",
    "scope", "starting-style", "stylesheet", "view-transition", "annotation",
}
_TITLE_RE   = re.compile(r"<title>.*?</title>", re.IGNORECASE)

_BRAND_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'(<h1\s+class\s*=\s*["\']home-header["\'][^>]*>).*?(</h1>)', re.I),
     rf'\g<1>{CHANNEL_NAME}\g<2>'),
    (re.compile(r'(<div\s+class\s*=\s*["\']quiz-brand[^"]*["\'][^>]*>).*?(</div>)', re.I),
     r'\g<1>A2Z Updates\g<2>'),
    (re.compile(r'(<div\s+class\s*=\s*["\']brand-badge["\'][^>]*>).*?(</div>)', re.I),
     r'\g<1>A2Z Updates\g<2>'),
    (re.compile(r'(<h1\s+class\s*=\s*["\']main-title["\'][^>]*>).*?(</h1>)', re.I),
     r'\g<1>A2Z Updates\g<2>'),
]


def universal_rebrand(html: str) -> Tuple[str, int]:
    """Replace ALL brand references → A2Z Updates.  Works on ANY mock."""
    changes = 0
    content = html

    # 1) t.me links
    seen: set = set()
    for m in _TME_LINK_RE.finditer(content):
        seen.add(m.group(1))
    for link in sorted(seen, key=len, reverse=True):
        if link == "A2Zupdates4U":
            continue
        old = f"https://t.me/{link}"
        n = content.count(old)
        if n:
            content = content.replace(old, CHANNEL_LINK)
            changes += n

    # 2) @handles (avoid URLs already processed)
    handles: set = set()
    for m in _HANDLE_RE.finditer(content):
        h = m.group(1)
        before = content[max(0, m.start() - 40):m.start()]
        if "t.me/A2Zupdates4U" not in before and h != "A2Zupdates4U" and h.lower() not in _HANDLE_BLACKLIST:
            handles.add(h)
    for h in sorted(handles, key=len, reverse=True):
        old = f"@{h}"
        n = content.count(old)
        if n:
            content = content.replace(old, CHANNEL_HANDLE)
            changes += n

    # 3) <title>
    if _TITLE_RE.search(content):
        content = _TITLE_RE.sub(f"<title>{CHANNEL_NAME}</title>", content, count=1)
        changes += 1

    # 4) Brand‑container patterns
    for pat, repl in _BRAND_PATTERNS:
        new, n = pat.subn(repl, content)
        if n:
            content = new
            changes += n

    # 5) "Join Telegram @XXX"
    n = 0
    content, n = re.subn(r"Join Telegram @\w+", f"Join Telegram {CHANNEL_HANDLE}", content)
    changes += n

    # 6) Fix visible text of <a> tags whose href was already rebranded
    content, n = re.subn(
        r'(<a\s+[^>]*href="https://t\.me/A2Zupdates4U"[^>]*>)\s*@\w+\s*(</a>)',
        rf"\g<1>{CHANNEL_HANDLE}\g<2>",
        content,
    )
    changes += n

    return content, changes


async def _gemini_brand_detect(html: str) -> dict:
    """Use Gemini to detect brand-specific text that regex patterns missed."""
    # Strip script/style to reduce noise, keep only visible text
    visible = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.I)
    visible = re.sub(r'<style[^>]*>.*?</style>', '', visible, flags=re.DOTALL | re.I)
    visible = re.sub(r'<[^>]+>', ' ', visible)
    visible = re.sub(r'\s+', ' ', visible).strip()[:5000]

    prompt = f"""Analyze this HTML mock test text. Find ONLY brand-specific promotional text (channel names, company names, slogans, brand badges, watermark text). 

Do NOT include:
- Mock/test names (e.g. "SP-MOCK 10", "MOCK TEST", "Practice Test")
- Subject names (e.g. "Mathematics", "English", "MATHS")
- Quiz questions, answers, options, explanations
- Instructions text
- Common words

Text from HTML:
{visible}

Return a JSON object with a "brands" array.
Example: {{"brands": ["SADHANA PRIME MOCKS", "JAY SHREE RAM", "@SomeChannel"]}}

Only return the JSON, no other text"""

    try:
        raw = await _gemini_call(prompt, GEMINI_MODEL, max_retries=2)
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)
        return data
    except Exception as e:
        log.warning("Gemini brand detection failed: %s", e)
        return {"brands": []}


def _apply_brand_replacements(html: str, brands: list) -> Tuple[str, int]:
    """Replace detected brand strings with A2Z branding."""
    changes = 0
    content = html
    for brand in sorted(brands, key=len, reverse=True):
        brand = brand.strip()
        if not brand or len(brand) < 3:
            continue
        # Skip quiz/mock identifiers (these are NOT brand text)
        skip_words = ["question", "answer", "option", "correct", "explanation", "meaning",
                      "direction", "solve", "evaluate", "find", "choose", "select", "mcq",
                      "mock", "mock test", "sp-mock", "test series", "quiz", "practice"]
        if any(w in brand.lower() for w in skip_words):
            continue
        # Skip A2Z references
        if "A2Z" in brand.upper() or "a2z" in brand.lower():
            continue
        # Skip very short or single-word brands that look like common words
        if len(brand.split()) == 1 and len(brand) < 6:
            continue
        n = content.count(brand)
        if n:
            content = content.replace(brand, "A2Z Updates")
            changes += n
            log.info("Gemini rebrand: '%s' → 'A2Z Updates' (%d occurrences)", brand, n)
    return content, changes


# ═══════════════════════════════════════════════════════════════════════════
# UNIVERSAL QUESTION EXTRACTOR  (format‑agnostic — handles ANY mock)
# ═══════════════════════════════════════════════════════════════════════════

# — Any const/let/var ___ = [  or  {  with ANY variable name —
_ANY_ARRAY_RE = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(\[)", re.DOTALL)
_ANY_OBJ_RE   = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(\{)", re.DOTALL)

# — Key alias maps — every known naming convention —
_TEXT_KEYS = ["text", "q", "question", "ques", "sentence", "statement", "q_en", "q_hi",
             "title", "prompt", "body", "en", "english", "phrase", "stem", "passage"]
_OPTIONS_KEYS = ["options", "choices", "opts", "answers", "options_en", "options_hi",
                 "alternatives", "variants", "choice", "optionsList", "opts_en", "opts_hi"]
_CORRECT_KEYS = ["correctIndex", "correct", "answer", "right", "key", "correct_answer",
                 "right_answer", "answerIndex", "answer_index", "answerindex"]
_EXPL_KEYS = ["explanation", "meaning_en", "meaning_hi", "explain", "solution", "sol",
              "description", "note", "exp", "soln", "explaination", "a", "answer",
              "word", "hindi", "solution_en", "solution_hi"]


def _extract_json_block(text: str, start_idx: int, opener: str) -> Optional[str]:
    closer = "}" if opener == "{" else "]"
    depth = 0
    i = start_idx
    while i < len(text):
        ch = text[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start_idx:i + 1]
        elif ch in ('"', "'"):
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        i += 1
    return None


def _try_parse(raw: str) -> Any:
    for fn in (
        json.loads,
        lambda x: json.loads(re.sub(r",\s*([}\]])", r"\1", x)),
        lambda x: json.loads(_js_to_json(x)),
    ):
        try:
            return fn(raw)
        except Exception:
            continue
    return None


def _js_to_json(js_text: str) -> str:
    """Convert a JavaScript‑style object literal (unquoted keys) to valid JSON."""
    s = re.sub(r'([{,])\s*([a-zA-Z_$][\w$]*)\s*:', r'\1"\2":', js_text)
    s = re.sub(r'^\s*([a-zA-Z_$][\w$]*)\s*:', r'"\1":', s)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    s = s.replace("\\'", "'")
    return s


def _pick_val(obj: dict, keys: list, default=None):
    """Return the first matching key's value from obj."""
    for k in keys:
        v = obj.get(k)
        if v is not None and v != "":
            return v
    return default


def _score_question(q: dict) -> int:
    """Score a dict on how likely it is a quiz question. Higher = more likely."""
    score = 0
    has_text = any(isinstance(q.get(k), str) and q.get(k).strip() for k in _TEXT_KEYS)
    has_opts = any(isinstance(q.get(k), list) and len(q.get(k)) > 0 for k in _OPTIONS_KEYS)
    has_correct = any(q.get(k) not in (None, -1, "") for k in _CORRECT_KEYS)
    has_expl = any(isinstance(q.get(k), str) and q.get(k).strip() for k in _EXPL_KEYS)
    if has_text: score += 3
    if has_opts: score += 3
    if has_correct: score += 2
    if has_expl: score += 1
    return score


def _normalise_question(q: dict) -> dict:
    """Convert a question dict (any keys) into the standard internal format."""
    text = _pick_val(q, _TEXT_KEYS, "")
    if not text:
        text = str(q.get("q_en", q.get("q_hi", q.get("phrase", ""))))
    # Also capture Hindi/bilingual version if available
    text_hi = q.get("q_hi") or q.get("question_hi") or q.get("text_hi") or ""
    if not text_hi and q.get("q_en") and q.get("q_hi"):
        text = q.get("q_en", text)
        text_hi = q.get("q_hi", text)
    
    options = []
    options_hi = []
    for k in _OPTIONS_KEYS:
        v = q.get(k)
        if isinstance(v, list) and v:
            options = [str(o) for o in v]
            break
    # Try Hindi options
    for k in ["options_hi", "opts_hi", "choices_hi"]:
        v = q.get(k)
        if isinstance(v, list) and v:
            options_hi = [str(o) for o in v]
            break
    
    correct = -1
    for k in _CORRECT_KEYS:
        v = q.get(k)
        if v is not None and v != -1 and v != "":
            try:
                correct = int(v)
            except (ValueError, TypeError):
                # Try letter to index conversion (a→0, b→1)
                if isinstance(v, str) and len(v) == 1 and v.isalpha():
                    correct = ord(v.lower()) - ord('a')
            break
    
    explanation = _pick_val(q, _EXPL_KEYS, "")
    if not explanation:
        explanation = str(q.get("meaning_en", q.get("meaning_hi", q.get("word", q.get("hindi", "")))))
    if explanation and q.get("pos") and q.get("hindi"):
        extra = f" ({q['pos']}) — {q['hindi']}"
        if extra not in explanation:
            explanation = explanation + extra
    
    result = {
        "text": text,
        "options": options,
        "correctIndex": correct,
        "explanation": explanation,
        "_raw": q,
    }
    # Add bilingual fields if available
    if text_hi and text_hi != text:
        result["text_hi"] = text_hi
    if options_hi:
        result["options_hi"] = options_hi
    # Capture Hindi explanation too
    expl_hi = q.get("solution_hi") or q.get("meaning_hi") or q.get("explanation_hi") or ""
    if expl_hi and expl_hi != explanation:
        result["explanation_hi"] = expl_hi
    
    return result


# ── HTML DOM‑based question extraction (for mocks with inline HTML questions + test object) ──

def _extract_html_questions(html: str) -> Optional[List[Dict]]:
    """Extract questions from HTML DOM (q-card format) or questions.push() format."""
    out = _extract_qcard_questions(html)
    if out:
        return out
    out = _extract_push_questions(html)
    if out:
        return out
    return _extract_qblock_questions(html)


def _extract_qcard_questions(html: str) -> Optional[List[Dict]]:
    """Extract from <div class='q-card'> format (Mocks Wallah DOM style)."""
    # Find card divs by id pattern: id="q67ab..."
    card_ids = re.findall(r'<div[^>]*\bclass\s*=\s*["\']q-card["\'][^>]*\bid\s*=\s*["\']q([a-f0-9]+)["\']', html, re.I)
    if len(card_ids) < 2:
        return None

    # Parse the test object for correct answers
    test_correct = {}
    test_match = re.search(r'(?:const|let|var)\s+test\s*=\s*(\{.*?\});\s*(?:\n|$)', html, re.DOTALL)
    if test_match:
        try:
            test_block = test_match.group(1)
            test_block = re.sub(r',\s*([}\]])', r'\1', test_block)  # remove trailing commas
            test_data = json.loads(_js_to_json(test_block))
            test_correct = test_data.get("correct", {})
        except Exception:
            pass

    # Parse qMap for section info
    q_map = {}
    map_match = re.search(r'qMap\s*:\s*(\{.*?\}),\s*(?:submitted|sections)', html, re.DOTALL)
    if map_match:
        try:
            map_block = map_match.group(1)
            map_block = re.sub(r',\s*([}\]])', r'\1', map_block)
            q_map = json.loads(_js_to_json(map_block))
        except Exception:
            pass

    out = []
    for qid in card_ids:
        # Find card block - everything from <div class="q-card" id="q{qid}" to the matching </div>
        card_start = html.find(f'id="q{qid}"')
        if card_start < 0:
            continue
        # Find the opening div tag position
        div_start = html.rfind('<div', 0, card_start)
        card_block = _extract_json_block(html, div_start + 4, "{")  # skip '<div'
        # Actually for HTML we need different bracket matching
        card_block = _extract_tag_block(html, card_start)

        if not card_block:
            continue

        # Question text
        qt_match = re.search(r'<div[^>]*class\s*=\s*["\']q-text["\'][^>]*>(.*?)</div>\s*(?=<div[^>]*class\s*=\s*["\']options)', card_block, re.DOTALL | re.I)
        text = ""
        if qt_match:
            text = re.sub(r'<[^>]+>', ' ', qt_match.group(1))
            text = re.sub(r'\s+', ' ', text).strip()

        # Options
        options = []
        for om in re.finditer(r'<div[^>]*class\s*=\s*["\']option-text["\'][^>]*>(.*?)</div>', card_block, re.DOTALL | re.I):
            opt_text = re.sub(r'<[^>]+>', ' ', om.group(1))
            opt_text = re.sub(r'\s+', ' ', opt_text).strip()
            if opt_text:
                options.append(opt_text)

        # Solution
        sol_match = re.search(r'<div[^>]*class\s*=\s*["\']solution-content["\'][^>]*>(.*?)</div>\s*</div>', card_block, re.DOTALL | re.I)
        explanation = ""
        if sol_match:
            explanation = re.sub(r'<[^>]+>', ' ', sol_match.group(1))
            explanation = re.sub(r'\s+', ' ', explanation).strip()

        # Section
        sec_match = re.search(r'<div[^>]*class\s*=\s*["\']q-section["\'][^>]*>(.*?)</div>', card_block, re.DOTALL | re.I)
        section_name = re.sub(r'<[^>]+>', '', sec_match.group(1)).strip() if sec_match else ""

        # Correct answer from test object
        correct_idx = -1
        if qid in test_correct:
            try:
                correct_idx = int(test_correct[qid])
            except (ValueError, TypeError):
                pass

        if not text:
            continue

        out.append({
            "text": text,
            "options": options,
            "correctIndex": correct_idx,
            "explanation": explanation,
            "_raw": {"section": section_name, "qid": qid},
        })

    return out if out else None


def _extract_tag_block(html: str, start_pos: int) -> Optional[str]:
    """Extract an HTML tag block (like a div) by counting opening/closing tags."""
    # Find the start of the tag
    tag_start = html.rfind('<', 0, start_pos + 10)
    if tag_start < 0:
        return None
    
    # Find tag name
    tag_match = re.match(r'<\s*(\w+)', html[tag_start:])
    if not tag_match:
        return None
    tag_name = tag_match.group(1)
    
    # Count matching tags
    depth = 0
    i = tag_start
    open_tag = re.compile(r'<\s*' + tag_name + r'[\s>]', re.I)
    close_tag = re.compile(r'</\s*' + tag_name + r'\s*>', re.I)
    
    while i < len(html):
        om = open_tag.match(html, i)
        cm = close_tag.match(html, i)
        if om:
            depth += 1
            i = om.end()
        elif cm:
            depth -= 1
            if depth == 0:
                return html[tag_start:cm.end()]
            i = cm.end()
        else:
            i += 1
    return None


def _extract_push_questions(html: str) -> Optional[List[Dict]]:
    """Extract from questions.push({...}) format (mocks_wallah / p* series)."""
    # Find all questions.push({...}) blocks
    push_pattern = re.compile(r'questions\.push\(\s*(\{.*?\})\s*\)', re.DOTALL)
    pushes = push_pattern.findall(html)
    if len(pushes) < 2:
        return None

    out = []
    for push_block in pushes:
        try:
            # JS object to JSON
            cleaned = _js_to_json(push_block)
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
            data = json.loads(cleaned)
        except Exception:
            continue

        text = data.get("question_en") or data.get("question_hi") or data.get("question") or ""
        options = data.get("options_en") or data.get("options_hi") or data.get("options") or []
        solution = data.get("solution_en") or data.get("solution_hi") or data.get("solution") or ""
        correct_raw = data.get("correct", -1)
        section = data.get("section", "")

        # Convert correct from letter (a/b/c/d) to index (0/1/2/3)
        correct_idx = -1
        if isinstance(correct_raw, str) and len(correct_raw) == 1:
            correct_idx = ord(correct_raw.lower()) - ord('a')
        elif isinstance(correct_raw, (int, float)):
            correct_idx = int(correct_raw)
            if correct_idx > 26:  # likely 1-based, not 0-based
                correct_idx = 0

        if not text:
            continue

        out.append({
            "text": text,
            "options": [str(o) for o in options] if options else [],
            "correctIndex": correct_idx,
            "explanation": str(solution) if solution else "",
            "_raw": {"section": section, "id": data.get("id", "")},
        })

    return out if out else None


def _extract_qblock_questions(html: str) -> Optional[List[Dict]]:
    """Fallback: extract from generic q-block / question-box divs."""
    for container_cls in ["question-box", "q-block"]:
        blocks = re.findall(
            rf'<div[^>]*class\s*=\s*["\'][^"\']*{container_cls}[^"\']*["\'][^>]*>(.*?)(?=<div[^>]*class\s*=\s*["\'][^"\']*(?:{container_cls}|question-box|q-block)|</body>)',
            html, re.DOTALL | re.I
        )
        if len(blocks) >= 2:
            out = []
            for block in blocks:
                text_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL | re.I)
                text = re.sub(r'<[^>]+>', '', text_match.group(1)).strip() if text_match else ""
                opts = []
                for om in re.finditer(r'<button[^>]*class\s*=\s*["\'][^"\']*opt[^"\']*["\'][^>]*>(.*?)</button>', block, re.DOTALL | re.I):
                    opts.append(re.sub(r'<[^>]+>', '', om.group(1)).strip())
                if text:
                    out.append({"text": text, "options": opts, "correctIndex": -1, "explanation": "", "_raw": {}})
            if out:
                return out
    return None


def extract_questions(html: str) -> Tuple[Optional[List[Dict]], str]:
    """Extract question objects from ANY mock HTML — no assumptions about variable/key names."""
    content = html
    candidates: List[Tuple[List[Dict], str, int]] = []

    # — Strategy A:  const/let/var ANY = { ... "questions": [...] ... } —
    for m in _ANY_OBJ_RE.finditer(content):
        var_name = m.group(1)
        block = _extract_json_block(content, m.start(2), "{")
        if not block:
            continue
        data = _try_parse(block)
        if not isinstance(data, dict):
            continue
        qs = data.get("questions") or data.get("quiz") or data.get("items")
        if isinstance(qs, list) and qs:
            norm = [_normalise_question(q) for q in qs if isinstance(q, dict)]
            if norm:
                score = sum(_score_question(n) for n in norm)
                candidates.append((norm, f"obj:{var_name}", score))
            elif qs and all(isinstance(q, dict) for q in qs):
                norm = [_normalise_question(q) for q in qs]
                candidates.append((norm, f"obj:{var_name}", 1))

    # — Strategy B:  const/let/var ANY = [ { ... }, ... ] —
    for m in _ANY_ARRAY_RE.finditer(content):
        var_name = m.group(1)
        block = _extract_json_block(content, m.start(2), "[")
        if not block:
            continue
        data = _try_parse(block)
        if not isinstance(data, list):
            continue
        if len(data) < 2:
            continue
        dicts = [q for q in data if isinstance(q, dict)]
        if len(dicts) < 2:
            continue
        norm = [_normalise_question(q) for q in dicts]
        score = sum(_score_question(n) for n in norm)
        if score > 0:
            candidates.append((norm, f"arr:{var_name}", score))

    if not candidates:
        # — Strategy C: HTML-embedded questions (no JS data) —
        # Look for <div class="q-card"> or similar question containers
        html_qs = _extract_html_questions(content)
        if html_qs:
            log.info("Extracted %d questions from HTML DOM (score=%d)", len(html_qs), sum(_score_question(q) for q in html_qs))
            return html_qs, "html:questions"

        return None, "none"

    # Pick the best candidate: prefer ones with options, higher score, more questions
    def _candidate_key(c):
        norm_list, block_id, score = c
        # Bonus: prefer candidates that have options in their questions
        has_opts = any(q.get("options") and len(q["options"]) > 0 for q in norm_list)
        opt_bonus = 100 if has_opts else 0
        # Penalize likely flashcard arrays (have "word" key but no "q" or "question" key)
        first = norm_list[0] if norm_list else {}
        raw = first.get("_raw", {})
        is_flashcard = ("word" in raw and "pos" in raw and "q" not in raw and "question" not in raw)
        flash_penalty = -50 if is_flashcard else 0
        return (score + opt_bonus + flash_penalty, len(norm_list))
    
    candidates.sort(key=_candidate_key, reverse=True)
    best = candidates[0]
    log.info("Extracted %d questions from %s (score=%d)", len(best[0]), best[1], best[2])
    return best[0], best[1]


# ═══════════════════════════════════════════════════════════════════════════
# GEMINI REPHRASING ENGINE  (40‑key rotating pool)
# ═══════════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are a precise language rephraser for quiz questions.
Your job is to produce BILINGUAL (English + Hindi) output for every question.

STRICT RULES:
1. MEANING, DIFFICULTY LEVEL, and CORRECT ANSWER must stay 100% identical.
2. Only change: vocabulary, sentence structure, phrasing.
3. NEVER add, remove, or alter any fact, name, date, number, or concept.
4. NEVER make a question easier or harder.
5. NEVER change the order of options (correctIndex stays same).
6. Provide BOTH "text" (English) AND "text_hi" (Hindi) for every question.
   - If Hindi version is provided, rephrase it naturally.
   - If Hindi is NOT provided or empty, CREATE a proper Hindi translation.
7. Provide BOTH "options" (English) AND "options_hi" (Hindi) arrays.
   - If Hindi options are provided, rephrase them.
   - If NOT provided, translate each option to Hindi.
8. EXPLANATION QUALITY (CRITICAL — TEACHER-STYLE HANDWRITTEN SOLUTION):
   - Write like a TOP TEACHER's personal notes: crisp, clear, step-by-step.
   - NO AI-sounding phrases like "The correct answer is...", "Hence proved", "Therefore option..."
   - Just explain the logic naturally as if writing on a whiteboard.
   - MATH: Show formula → plug values → step-by-step working → final answer.
     Use ×, ÷, √, ², ³, = signs. Example: "7 ka unit digit cycle = 4 (7,9,3,1). 103÷4 = 25 remainder 3. Teesri position = 3."
   - REASONING: Break the pattern/logic into simple steps. Show the trick.
   - ENGLISH: Give word meaning, root/origin if helpful, memory trick (mnemonic).
   - GK/GS: Give key fact + 1-line context. Link to current affairs if relevant.
   - Keep explanations CONCISE — 3-5 lines max. Don't repeat the question.
   - Use bullet points (•) or numbered steps (1. 2. 3.) for clarity.
   - Provide BOTH "explanation" (English) AND "explanation_hi" (Hindi).
9. Keep all HTML tags like <b>, <i> intact.
10. Append this exact CTA on a NEW LINE at the end of every explanation (EN and HI):
    "---\\n📢 Join A2Z Updates for more mocks: https://t.me/A2Zupdates4U"

11. TAXONOMY TAGS (for every question):
    - Analyze the question content and assign: subject, chapter, topic, subtopic.
    - Subjects: "Quantitative Aptitude", "English Language", "General Awareness", "Reasoning"
    - Chapters under Quant: "Arithmetic", "Algebra", "Geometry", "Trigonometry", "Data Interpretation", "Number System"
    - Chapters under English: "Vocabulary", "Grammar", "Comprehension", "Error Detection"
    - Chapters under GA: "History", "Geography", "Polity", "Economics", "Science", "Current Affairs"
    - Chapters under Reasoning: "Verbal Reasoning", "Non-Verbal Reasoning"
    - Assign difficulty_level: "easy" / "medium" / "hard"
    - Assign cognitive_level: "knowledge" (rote recall) / "application" (apply formula/logic) / "analysis" (multi-step reasoning)
    - concept_tags: array of specific tags like ["LCM-based", "ratio-based", "formula-based", "trick", "rule-based", "memory-based"]

Output ONLY this valid JSON:
{"questions": [ { "text": "...", "text_hi": "...", "options": [...], "options_hi": [...], "correctIndex": N, "explanation": "...", "explanation_hi": "...", "subject": "...", "chapter": "...", "topic": "...", "subtopic": "...", "difficulty": "medium", "cognitive": "knowledge", "tags": ["..."] }, ... ] }"""


async def _gemini_call(payload: str, model_name: str, max_retries: int = 6, state: Optional['ProcessState'] = None) -> str:
    """Call Gemini with key rotation + retries on 429."""
    import google.generativeai as genai

    for attempt in range(max_retries):
        key = key_manager.get_next_key()
        if not key:
            log.warning("All keys cooling – waiting 30 s (attempt %d/%d)", attempt + 1, max_retries)
            if state:
                await state.update(section_status="⏳ All keys cooling — waiting...")
            await asyncio.sleep(30)
            continue

        # Find key index for display
        key_idx = 0
        for k_ in key_manager.keys:
            if k_["key"] == key:
                key_idx = k_["index"]
                break

        if state:
            await state.update(
                current_model=model_name,
                current_key=key_idx,
                attempt=attempt + 1,
                max_attempts=max_retries,
                section_status=f"🤖 {model_name}  🔑 Key #{key_idx}  Attempt {attempt + 1}/{max_retries}",
            )

        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(model_name, system_instruction=SYSTEM_PROMPT)
            response = await model.generate_content_async(payload)
            key_manager.mark_success(key)
            return response.text.strip()
        except Exception as e:
            msg = str(e)
            key_manager.mark_cooling(key, msg)
            log.warning("%s attempt %d failed: %s", model_name, attempt + 1, msg[:120])
            if state:
                await state.update(section_status=f"⚠️ Attempt {attempt + 1} failed — rotating key...")
            await asyncio.sleep(1)

    raise RuntimeError(f"Model {model_name} exhausted after {max_retries} retries.")


async def rephrase_via_gemini(questions: List[Dict], model_override: str = "", state: Optional['ProcessState'] = None) -> Optional[List[Dict]]:
    """Rephrase questions using the 40‑key pool + model fallback chain.  Returns None on total failure."""
    try:
        import google.generativeai  # noqa: F401 – verify import
    except ImportError:
        log.warning("google-generativeai not installed – pip install google-generativeai")
        return None

    # Build model fallback chain
    chain = [model_override] if model_override else [GEMINI_MODEL]
    chain += GEMINI_FALLBACK_MODELS
    seen_set = set()
    chain = [m for m in chain if not (m in seen_set or seen_set.add(m))]

    # Build payload objects with bilingual fields
    payload_qs = []
    for q in questions:
        entry = {
            "text": q["text"],
            "text_hi": q.get("text_hi", ""),
            "options": q["options"],
            "options_hi": q.get("options_hi", []),
            "correctIndex": q.get("correctIndex", -1),
            "explanation": q.get("explanation", ""),
            "explanation_hi": q.get("explanation_hi", ""),
        }
        payload_qs.append(entry)

    BATCH_SIZE = 8
    batches = [payload_qs[i:i + BATCH_SIZE] for i in range(0, len(payload_qs), BATCH_SIZE)]
    all_results = []

    for batch_idx, batch in enumerate(batches):
        batch_msg = json.dumps({"questions": batch}, ensure_ascii=False, indent=2)
        batch_start = time.time()

        if state:
            await state.update(section_status=f"📦 Batch {batch_idx+1}/{len(batches)} — sending {len(batch)} Qs...")

        batch_ok = False
        last_error = None
        for model_name in chain:
            try:
                raw = await _gemini_call(batch_msg, model_name, state=state)
            except Exception as exc:
                last_error = exc
                log.warning("Batch %d model %s failed: %s", batch_idx + 1, model_name, exc)
                if state:
                    await state.update(section_status=f"⚠️ Batch {batch_idx+1}: {model_name} failed, trying fallback...")
                continue

            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            try:
                result = json.loads(raw)
                rephrased = result.get("questions", result if isinstance(result, list) else [])
            except json.JSONDecodeError:
                log.error("Batch %d %s returned invalid JSON", batch_idx + 1, model_name)
                continue

            if not isinstance(rephrased, list) or len(rephrased) != len(batch):
                log.error("Batch %d %s returned %d items, expected %d", batch_idx + 1, model_name,
                          len(rephrased) if isinstance(rephrased, list) else 0, len(batch))
                continue

            # Merge rephrased batch back into original question dicts
            for j, q in enumerate(batch):
                rq = rephrased[j]
                orig_idx = batch_idx * BATCH_SIZE + j
                merged = dict(questions[orig_idx])
                merged["text"] = rq.get("text", merged["text"])
                merged["explanation"] = rq.get("explanation", merged["explanation"])
                if "options" in rq and rq["options"] and merged.get("options"):
                    merged["options"] = rq["options"]
                # Bilingual fields
                if rq.get("text_hi"):
                    merged["text_hi"] = rq["text_hi"]
                if rq.get("options_hi"):
                    merged["options_hi"] = rq["options_hi"]
                if rq.get("explanation_hi"):
                    merged["explanation_hi"] = rq["explanation_hi"]
                all_results.append(merged)

            batch_ok = True
            break

        if not batch_ok:
            log.error("Batch %d/%d failed on all models. Last error: %s", batch_idx + 1, len(batches), last_error)
            return None

        # Update progress
        duration = time.time() - batch_start
        if state:
            state.durations.append(duration)
            await state.update(done=len(all_results))

        log.info("Batch %d/%d ✅ (%d Qs, %.1fs) — total done: %d", batch_idx + 1, len(batches), len(batch), duration, len(all_results))

    log.info("✅ Rephrased %d questions across %d batches", len(all_results), len(batches))
    return all_results


# ═══════════════════════════════════════════════════════════════════════════
# HTML REBUILDER – inject rephrased data back (universal)
# ═══════════════════════════════════════════════════════════════════════════
def _find_var_block(html: str, var_name: str, bracket: str) -> Optional[Tuple[int, str]]:
    """Find a JS variable assignment block in HTML. Returns (start_idx, block_text) or None."""
    escaped_bracket = re.escape(bracket)
    pattern = re.compile(
        r"(?:const|let|var)\s+" + re.escape(var_name) + r"\s*=\s*(" + escaped_bracket + r")",
        re.DOTALL,
    )
    m = pattern.search(html)
    if not m:
        return None
    block = _extract_json_block(html, m.start(1), bracket)
    if not block:
        return None
    return m.start(), block


def _detect_keys(original_q: dict) -> dict:
    """Given one raw question dict, figure out which keys map to what."""
    mapping = {"text_key": None, "options_key": None, "expl_key": None}
    for k in _TEXT_KEYS:
        if k in original_q and isinstance(original_q[k], str) and original_q[k].strip():
            mapping["text_key"] = k
            break
    for k in _OPTIONS_KEYS:
        v = original_q.get(k)
        if isinstance(v, list) and v:
            mapping["options_key"] = k
            break
    for k in _EXPL_KEYS:
        if k in original_q and isinstance(original_q[k], str) and original_q[k].strip():
            mapping["expl_key"] = k
            break
    return mapping


def rebuild_html(html: str, questions: List[Dict], ttype: str) -> str:
    """Rebuild HTML by injecting rephrased text/explanation back into the original JS block."""
    content = html
    parts = ttype.split(":", 1)
    if len(parts) != 2:
        return content
    kind, var_name = parts[0], parts[1]

    bracket = "{" if kind == "obj" else "["
    found = _find_var_block(content, var_name, bracket)
    if found is None:
        for m in re.finditer(r"(?:const|let|var)\s+(\w+)\s*=\s*([\[\{])", content, re.DOTALL):
            if m.group(1) == var_name:
                block = _extract_json_block(content, m.start(2), m.group(2))
                if block:
                    found = (m.start(), block)
                    bracket = m.group(2)
                    break
    if found is None:
        log.warning("rebuild_html: could not find block for %s", var_name)
        return content

    _, block = found
    data = _try_parse(block)
    if data is None:
        log.warning("rebuild_html: could not parse block for %s", var_name)
        return content

    q_list: list = []
    if isinstance(data, list):
        q_list = data
    elif isinstance(data, dict):
        q_list = data.get("questions") or data.get("quiz") or data.get("items") or []
    else:
        return content

    if not q_list or not isinstance(q_list, list):
        return content

    first = q_list[0] if q_list else {}
    key_map = _detect_keys(first) if isinstance(first, dict) else {}

    for i, q in enumerate(questions):
        if i >= len(q_list):
            break
        r = q_list[i]
        if not isinstance(r, dict):
            continue

        if key_map.get("text_key") and key_map["text_key"] in r:
            r[key_map["text_key"]] = q["text"]
        else:
            for tk in _TEXT_KEYS:
                if tk in r:
                    r[tk] = q["text"]
                    break

        if key_map.get("options_key") and key_map["options_key"] in r:
            if q.get("options"):
                opts = r[key_map["options_key"]]
                if isinstance(opts, list) and len(opts) == len(q["options"]):
                    for j in range(len(opts)):
                        opts[j] = q["options"][j]
        else:
            for ok in _OPTIONS_KEYS:
                if ok in r and q.get("options"):
                    opts = r[ok]
                    if isinstance(opts, list) and len(opts) == len(q["options"]):
                        for j in range(len(opts)):
                            opts[j] = q["options"][j]
                        break

        expl_text = q.get("explanation", "")
        if key_map.get("expl_key") and key_map["expl_key"] in r:
            r[key_map["expl_key"]] = expl_text
        else:
            for ek in _EXPL_KEYS:
                if ek in r:
                    r[ek] = expl_text
                    break

    new_block = json.dumps(data, ensure_ascii=False, indent=2)
    content = content.replace(block, new_block, 1)
    return content


# ═══════════════════════════════════════════════════════════════════════════
# CTA INJECTION
# ═══════════════════════════════════════════════════════════════════════════
def inject_cta(questions: List[Dict]) -> List[Dict]:
    for q in questions:
        expl = q.get("explanation", "")
        if CTA not in expl:
            q["explanation"] = (expl or "Explanation not available.") + CTA
        # Also inject CTA into Hindi explanation
        expl_hi = q.get("explanation_hi", "")
        if expl_hi and CTA not in expl_hi:
            q["explanation_hi"] = expl_hi + CTA
    return questions


def inject_footer_banner(html: str) -> str:
    banner = (
        '\n<div style="text-align:center;padding:18px 20px;margin:20px 12px;'
        'background:linear-gradient(135deg,#6a5af9,#5041d5);color:#fff;'
        'border-radius:14px;font-family:Inter,sans-serif;">'
        '\n  📢 <b>Join A2Z Updates for more mocks</b><br>'
        f'\n  <a href="{CHANNEL_LINK}" style="color:#fff;font-weight:700;">{CHANNEL_LINK}</a>'
        '\n</div>\n'
    )
    if banner not in html:
        html = html.replace("</body>", banner + "</body>")
    return html


# ═══════════════════════════════════════════════════════════════════════════
# A2Z PREMIUM TEMPLATE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════
TEMPLATE_PATH = Path(__file__).parent / "a2z_template.html"


# ── Brand name stripping ────────────────────────────────────────────────
_KNOWN_BRAND_PATTERNS = [
    # Channel/creator brands (case-insensitive, word-boundary)
    re.compile(r'\bMocks\s*Wallah\b', re.I),
    re.compile(r'\bTHE\s+PUNDITS\b', re.I),
    re.compile(r'\bPUNDITS\b', re.I),
    re.compile(r'\bTeam\s*SPY\b', re.I),
    re.compile(r'\bADII\s*x?\s*ABH?I?I?\b', re.I),
    re.compile(r'\bSADHANA\b', re.I),
    re.compile(r'\bNight\b\s*-?\s*NewBie\b', re.I),
    re.compile(r'\bAI[_ ]?quiz[_ ]?bot[_ ]?pro\b', re.I),
    re.compile(r'\belite[_ ]?quiz[_ ]?bot\b', re.I),
    # Brand abbreviations (from known brands)
    re.compile(r'\bSP\b', re.I),                                           # Sadhana Prime abbreviation
    re.compile(r'\bBB\b(?=\s*-?\s*IDIOMS?\b)', re.I),                    # BB before IDIOMS
    # Fancy unicode brand chars (𝔸𝔻𝕀𝕀𝕏𝔸𝔹ℍ𝕀𝕀)
    re.compile(r'[𝔸𝔻]\s*[𝕀𝕏]\s*[𝕀𝕏]?\s*[𝔸𝔹]\s*[𝔹ℍ]\s*[𝕀𝕀]?', re.I),
    # Generic brand/channel patterns
    re.compile(r'\bTelegram\s+Channel\b', re.I),
    re.compile(r'@\S+'),
    re.compile(r'https?://\S+'),
    re.compile(r't\.me/\S+'),
]

# Emoji/fancy char strip regex (keep one instance)
_EMOJI_STRIP_RE = re.compile(
    r'[\U0001F300-\U0001F9FF\u2600-\u27BF\u2B50\u2728\uD83C\uDF3A\uD83D\uDC4D'
    r'✨🚩🌺💯⭐🔥🎯📚📰🔴💬✏️🧪🔀ℹ️🏆📊📲✈️🃏🗺️🧠🔤➡️👋🚀✔️🎯📝🎉📢📋📤🎲]',
)


def _detect_brand_abbreviations(html: str, name: str) -> str:
    """If CURRENT_MOCK_ID contains a known brand, try to strip its abbreviation from the name."""
    id_match = re.search(r'''(?:const|let|var)\s+\w*mock[_]?\w*id\w*\s*=\s*["']([^"']+)["']''', html, re.I)
    if not id_match:
        return name
    mock_id = id_match.group(1).strip()
    # Check if mock ID contains known brand substrings (underscore delimited)
    brand_keywords = {
        'SADHANA': ['SP'],
        'NIGHT': ['N'],
        'BLACKBOOK': ['BB'],
    }
    for brand, abbrs in brand_keywords.items():
        if brand.lower() in mock_id.lower():
            for abbr in abbrs:
                # Strip abbreviation if it appears as a standalone prefix in the name
                name = re.sub(rf'\b{re.escape(abbr)}\b\s*[-–—]?\s*', '', name, flags=re.I)
    return name


def _strip_brands(text: str) -> str:
    """Remove known brand/channel names, emojis, URLs, handles from a title string."""
    t = text.strip()
    # Strip emojis & fancy chars
    t = _EMOJI_STRIP_RE.sub('', t)
    # Strip known brands
    for pat in _KNOWN_BRAND_PATTERNS:
        t = pat.sub('', t)
    # Strip URLs and handles
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'@\S+', '', t)
    t = re.sub(r't\.me/\S+', '', t)
    # Clean up leftover separators (standalone, not within compound words)
    t = re.sub(r'\s+[\-\|—–]\s+[\-\|—–]\s+', ' — ', t)
    t = re.sub(r'\s+[\-\|—–]\s+', ' — ', t)
    # Remove leading/trailing separators left after brand stripping
    t = re.sub(r'^\s*[-–—]\s*', '', t)
    t = re.sub(r'\s*[-–—]\s*$', '', t)
    t = re.sub(r'\s+', ' ', t).strip(' -|—–•·')
    return t


def _extract_mock_info(html: str, questions: Optional[List[Dict]] = None) -> Tuple[str, str]:
    """Try to extract a meaningful mock title and section from the HTML or questions."""
    title = ""
    section = "General"

    # 0) PRIORITY: Extract from JS data blocks (settings.topic, quizData.settings, etc.)
    js_topic_patterns = [
        # PRIORITY 1: explicit mock name/title variables (most reliable)
        r'''(?:const|let|var)\s+\w*mock[_]?\w*name\w*\s*=\s*["']([^"']+)["']''',  # CURRENT_MOCK_NAME = "SP-MOCK 10"
        r'''(?:const|let|var)\s+\w*mock[_]?\w*title\w*\s*=\s*["']([^"']+)["']''',  # mock_title = "Mock Title"
        r'''["']mock_name["']\s*:\s*["']([^"']+)["']''',                          # "mock_name": "SP-MOCK 10"
        # PRIORITY 2: settings.topic from JS data
        r'''["']topic["']\s*:\s*"([^"]+)"''',                                     # "topic": "TODAY'S CURRENT AFFAIRS\n..."
        r"""["']topic["']\s*:\s*'([^']+)'""",                                     # 'topic': 'FIVE YEAR PLAN'
        r'''\btopic\s*:\s*["'](.+?)["']\s*[,}\n]''',                              # topic: "FIVE YEAR PLAN"
        r'''(?:const|let|var)\s+topic\s*=\s*["']([^"']+)["']''',                  # const topic = "FIVE YEAR PLAN"
        # PRIORITY 3: HTML element fallbacks
        r'''homeTopic["']?\s*[=:]\s*["']([^"']+)["']''',                          # homeTopic = "FIVE YEAR PLAN"
    ]
    for pat in js_topic_patterns:
        m = re.search(pat, html, re.I)
        if m:
            t = m.group(1).strip()
            # Take only the first line if multiline (strip URLs/telegram handles)
            t = t.split("\n")[0].split("\\n")[0].strip()
            t = _strip_brands(t)
            # Detect & strip brand abbreviations by cross-referencing with mock ID
            t = _detect_brand_abbreviations(html, t)
            if t and len(t) >= 2:
                title = t
                break

    # 1) Scan HTML for known title containers
    if not title:
        container_patterns = [
            r'<div\s+class\s*=\s*["\'][^"\']*title-text[^"\']*["\'][^>]*>\s*(.*?)\s*</div>',
            r'<h1\s+class\s*=\s*["\'][^"\']*main-title[^"\']*["\'][^>]*>\s*(.*?)\s*</h1>',
            r'<h1\s+class\s*=\s*["\'][^"\']*home-header[^"\']*["\'][^>]*>\s*(.*?)\s*</h1>',
            r'<h1[^>]*>\s*(.*?)\s*</h1>',
            r'<div\s+class\s*=\s*["\'][^"\']*quiz-brand[^"\']*["\'][^>]*>\s*(.*?)\s*</div>',
            r'<div\s+class\s*=\s*["\'][^"\']*brand-badge[^"\']*["\'][^>]*>\s*(.*?)\s*</div>',
            r'<span\s+class\s*=\s*["\'][^"\']*header-title[^"\']*["\'][^>]*>\s*(.*?)\s*</span>',
            r'<h2\s+class\s*=\s*["\'][^"\']*(?:section-title|test-title|mock-title)[^"\']*["\'][^>]*>\s*(.*?)\s*</h2>',
        ]
        for pat in container_patterns:
            m = re.search(pat, html, re.I | re.DOTALL)
            if m:
                t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                t = _strip_brands(t)
                if t and len(t) >= 3:
                    title = t
                    break

    # 2) Fallback: try <title> tag (split on separators, take best chunk)
    if not title:
        m = re.search(r"<title>(.*?)</title>", html, re.I)
        if m:
            t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            t = _strip_brands(t)
            if t and len(t) >= 3:
                title = t

    # 3) Try filename-based fallback (for mocks with no topic in content)
    if not title or len(title) < 3:
        # Look for section names that are specific (not generic like "English"/"Maths")
        section_names = set()
        for m2 in re.finditer(r'''["']name["']\s*:\s*["']([^"']+)["']''', html):
            sn = _strip_brands(m2.group(1))
            if sn and len(sn) > 2:
                section_names.add(sn)
        # Filter out generic section names
        _generic_sections = {"REASONING", "ENGLISH", "MATHS", "MATHEMATICS", "GK", "GENERAL AWARENESS",
                            "QUANTITATIVE APTITUDE", "QUANT", "MISCELLANEOUS", "COMPUTER KNOWLEDGE"}
        specific = [s for s in section_names if s.upper().strip() not in _generic_sections]
        if specific:
            title = " · ".join(sorted(specific)[:2])
        elif section_names:
            title = " · ".join(sorted(section_names)[:3])

    # Final fallback
    if not title or len(title) < 3:
        title = "Mock Test"

    # Append A2Z branding
    if "A2Z" not in title.upper():
        title = title + " — A2Z Mocks"

    # 3) Section from questions
    if questions:
        topics = set()
        for q in questions[:5]:
            raw = q.get("_raw", {})
            topic = raw.get("topic") or raw.get("subject") or raw.get("subtopic") or raw.get("section")
            if topic and isinstance(topic, str) and topic.strip():
                topics.add(topic.strip())
        if topics:
            section = ", ".join(sorted(topics)[:3])

    if section == "General" and questions:
        q_text = questions[0].get("text", "").lower()
        expl = questions[0].get("explanation", "").lower()
        if "idiom" in q_text or "idiom" in expl or "phrase" in expl:
            section = "Idioms & Phrases"
        elif "meaning" in q_text:
            section = "Vocabulary"
        else:
            raw = questions[0].get("_raw", {})
            sect = raw.get("section") or raw.get("sn")
            if sect:
                section = f"Section {sect}"

    return title, section


def _auto_fill_options(questions: List[Dict]) -> List[Dict]:
    """If questions have no options, generate distractors from other answers in the same set."""
    all_answers = []
    for q in questions:
        expl = q.get("explanation", "")
        # Strip CTA for clean answer pool
        if CTA in expl:
            expl = expl.split(CTA)[0]
        if expl and expl != "Explanation not available.":
            all_answers.append(expl)

    if len(all_answers) < 4:
        return questions

    for i, q in enumerate(questions):
        if q.get("options") and len(q["options"]) > 0:
            continue

        correct = q.get("explanation", "")
        if CTA in correct:
            correct = correct.split(CTA)[0]
        if not correct or correct == "Explanation not available.":
            continue

        pool = [a for a in all_answers if a != correct]
        if len(pool) < 3:
            continue
        distractors = random.sample(pool, 3)
        opts = distractors + [correct]
        random.shuffle(opts)
        q["options"] = opts
        q["correctIndex"] = opts.index(correct)

    return questions


def render_template(questions: List[Dict], mock_title: str = "A2Z Mock Test", section: str = "General",
                    timer_min: int = None, mock_id: str = "") -> str:
    """Inject questions into the premium A2Z template."""
    if not TEMPLATE_PATH.exists():
        log.warning("Template not found at %s — falling back to plain output", TEMPLATE_PATH)
        return None

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    total = len(questions)
    if timer_min is None:
        timer_min = max(5, int(total * 0.5))

    qs_for_js = []
    for q in questions:
        entry = {
            "text": q["text"],
            "options": q.get("options", []),
            "correctIndex": q.get("correctIndex", -1),
            "explanation": q.get("explanation", ""),
        }
        # Add bilingual fields if present
        if q.get("text_hi"):
            entry["text_hi"] = q["text_hi"]
        if q.get("options_hi"):
            entry["options_hi"] = q["options_hi"]
        if q.get("explanation_hi"):
            entry["explanation_hi"] = q["explanation_hi"]
        qs_for_js.append(entry)

    return (template
        .replace("{{MOCK_ID}}", mock_id)
        .replace("{{MOCK_TITLE}}", mock_title)
        .replace("{{SECTION_NAME}}", section)
        .replace("{{TOTAL_QS}}", str(total))
        .replace("{{TIMER_MINUTES}}", str(timer_min))
        .replace("{{QUESTIONS_JSON}}", json.dumps(qs_for_js, ensure_ascii=False)))


# ═══════════════════════════════════════════════════════════════════════════
# HIGH‑LEVEL PROCESSOR  (with progress tracking)
# ═══════════════════════════════════════════════════════════════════════════

class ProcessState:
    """Shared state for real‑time progress bar telemetry."""
    def __init__(self, total_questions: int = 0):
        self.start_time = time.time()
        self.total = max(total_questions, 1)
        self.done = 0
        self.phase = "rebranding"
        self.section_status = ""
        self.current_model = ""
        self.current_key = 0
        self.attempt = 0
        self.max_attempts = 6
        self.durations: List[float] = []
        self._lock = asyncio.Lock()

    async def update(self, **kwargs):
        async with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def key_stats(self):
        active = sum(1 for k_ in key_manager.keys if k_["status"] == "active" and not k_.get("dead"))
        cooling = sum(1 for k_ in key_manager.keys if k_["status"] == "cooling")
        dead = sum(1 for k_ in key_manager.keys if k_.get("dead"))
        return active, cooling, dead

    def overall_pct(self) -> int:
        return int((self.done / self.total) * 100) if self.total else 0

    def elapsed_str(self) -> str:
        s = int(time.time() - self.start_time)
        m, sec = divmod(s, 60)
        return f"{m}m {sec}s"

    def eta_str(self) -> str:
        if not self.durations or self.done == 0:
            return "..."
        avg = sum(self.durations) / len(self.durations)
        remaining = self.total - self.done
        eta_s = int(avg * remaining)
        if eta_s < 0:
            eta_s = 0
        m, sec = divmod(eta_s, 60)
        return f"{m}m {sec}s"

    def speed_per_min(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return 0
        return self.done / (elapsed / 60)

    def render_bar(self) -> str:
        pct = self.overall_pct()
        filled = int((pct / 100) * 14)
        return "█" * filled + "░" * (14 - filled)

    def render(self) -> str:
        active, cooling, dead = self.key_stats()
        pulse = "⣾⣽⣻⢿⡿⣟⣯⣷"[int(time.time() * 2) % 8]
        ts = time.strftime("%H:%M:%S")
        lines = [
            f"{pulse} Mock Customiser  {ts}",
            "━━━━━━━━━━━━━━━━━━━━━",
        ]
        if self.phase == "rephrasing":
            pct = self.overall_pct()
            lines.append(f"📊 {pct}%  [{self.render_bar()}]  {self.done}/{self.total} questions")
            lines.append(f"⏱ {self.elapsed_str()} elapsed  |  ETA ≈{self.eta_str()}  |  {self.speed_per_min():.1f} q/min")
            if self.section_status:
                lines.append(self.section_status)
            lines.append(f"🔑 Keys: 🟢{active} active  🟡{cooling} cooling  💀{dead} dead")
        elif self.phase == "rebranding":
            lines.append("🔍 Rebranding branding elements...")
            lines.append(f"🔑 Keys: 🟢{active} active  🟡{cooling} cooling  💀{dead} dead")
        elif self.phase == "extracting":
            lines.append(f"🔍 Extracting questions...  ({self.done} found)")
        elif self.phase == "rebuilding":
            lines.append("📦 Rebuilding HTML with changes...")
        elif self.phase == "done":
            lines.append("✅ Processing complete!")
        return "\n".join(lines)


async def _progress_loop(state: ProcessState, msg, interval: float = 3.0):
    """Update the Telegram message with live progress every `interval` seconds."""
    last_text = ""
    try:
        while state.phase != "done":
            text = state.render()
            if text != last_text:
                try:
                    await msg.edit_text(text)
                    last_text = text
                except Exception:
                    pass
            await asyncio.sleep(interval)
        # Final update
        text = state.render()
        if text != last_text:
            try:
                await msg.edit_text(text)
            except Exception:
                pass
    except asyncio.CancelledError:
        pass


async def process_mock(html: str, *, rephrase: bool = False, state: Optional['ProcessState'] = None) -> Tuple[str, Dict]:
    stats: Dict[str, int] = {"rebranded": 0, "extracted": 0, "rephrased": 0}

    # 1 – Universal rebrand (regex)
    if state:
        await state.update(phase="rebranding")
    content, stats["rebranded"] = universal_rebrand(html)

    # 1b – Gemini brand detection (catches what regex missed)
    brand_data = await _gemini_brand_detect(html)
    if brand_data.get("brands"):
        content2, extra = _apply_brand_replacements(content, brand_data["brands"])
        content = content2
        stats["rebranded"] += extra

    # 2 – Extract questions
    if state:
        await state.update(phase="extracting")
    questions, ttype = extract_questions(content)
    if questions:
        stats["extracted"] = len(questions)
        if state:
            await state.update(done=len(questions), total=len(questions))
    else:
        log.info("No questions found – rebrand only")
        content = inject_footer_banner(content)
        if state:
            await state.update(phase="done")
        return content, stats

    # 3 – Rephrase via Gemini
    if rephrase:
        if state:
            await state.update(phase="rephrasing", done=0, total=len(questions))
        rephrased = await rephrase_via_gemini(questions, state=state)
        if rephrased:
            questions = rephrased
            stats["rephrased"] = len(questions)

    # 4 – Auto-fill missing options, then inject CTA
    questions = _auto_fill_options(questions)
    questions = inject_cta(questions)

    # 5 – Render into premium A2Z template
    if state:
        await state.update(phase="rebuilding")
    title, section = _extract_mock_info(content, questions)
    # Generate unique mock ID
    mock_id = ""
    if DB_OK:
        mock_id = register_mock(0, title, topic=section, section=section,
                               source_file="cli_upload", question_count=len(questions),
                               timer_minutes=max(5, int(len(questions) * 0.5)))
        register_questions(mock_id, questions)
    elif questions:
        # Fallback: generate ID without DB
        import uuid as _uuid
        mock_id = "MOCK-" + _uuid.uuid4().hex[:8]
    content = render_template(questions, mock_title=title, section=section, mock_id=mock_id)
    if content is None:
        # Fallback: use original rebuild path
        content = rebuild_html(html, questions, ttype)
        content = inject_footer_banner(content)
    # Template already has A2Z branding / about / footer — no extra banner needed

    if state:
        await state.update(phase="done")

    return content, stats


# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT
# ═══════════════════════════════════════════════════════════════════════════
_pending: Dict[int, Dict] = {}

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.constants import ParseMode
    from telegram.ext import (
        Application, CallbackQueryHandler, CommandHandler,
        MessageHandler, filters, ContextTypes,
    )
    from telegram.helpers import escape_markdown
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Access-aware start — handles deep links for submit/auth/invite."""
    uid = update.effective_user.id
    uname = update.effective_user.username or ""
    fname = update.effective_user.first_name or ""

    if DB_OK:
        get_or_create_user(uid, uname, fname, update.effective_user.last_name or "")
        init_db(admin_ids=[7860164386], added_by=uid)
        # Apply gamification migration
        if GAME_OK:
            apply_gamification_migration(db_execute, db_commit)
            # Auto-apply rank decay on login
            decayed, lost = apply_rank_decay(db_execute, db_commit, uid)
            # Auto-create daily quest
            create_daily_quest(db_execute, db_commit, uid)
            # Update last active
            db_execute("UPDATE users SET last_active_date = date('now') WHERE telegram_id = ?", (uid,))

    # Handle deep links: /start submit_MOCK-xxx_score_...
    args = context.args
    if args and args[0].startswith("submit_"):
        await _handle_submit_link(update, args[0])
        return
    if args and args[0].startswith("inv_"):
        await _handle_invite_link(update, args[0])
        return
    if args and args[0].startswith("challenge_"):
        await _handle_challenge_link(update, args[0])
        return

    from telegram import ReplyKeyboardMarkup, KeyboardButton

    # Regular start — check access
    admin = is_admin(uid) if DB_OK else False

    if DB_OK:
        has_access, days_left, free_left = has_free_access(uid)
        user_row = db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (uid,))
        access_line = ""
        if has_access:
            access_line = f"\n🎫 *Access:* {days_left} days | {free_left} mocks left"
        else:
            access_line = f"\n⚠️ *Free tier:* {free_left} mocks left | /invite to unlock"
        if GAME_OK and user_row:
            xp = user_row["xp"] or 0
            rank = user_row["rank"] or "E"
            next_rank_info = xp_to_next_rank(xp) if xp else ("C", 300, 0)
            access_line += f"\n⚡ *Rank:* {RANK_NAMES.get(rank, 'Novice')} | *XP:* {xp}"
        stats = get_user_stats(uid) if DB_OK else {}
        stat_line = ""
        if stats and stats.get("total_mocks", 0) > 0:
            stat_line = f"\n📊 Mocks: {stats.get('total_mocks', 0)} | Accuracy: {stats.get('avg_accuracy', 0):.0f}%"
        fomo = get_fomo_message(dict(user_row), has_access, days_left) if GAME_OK and user_row else ""

        if admin:
            reply_kb = ReplyKeyboardMarkup([
                [KeyboardButton("🎨 Rebrand Mock"), KeyboardButton("📤 Upload Mock")],
                [KeyboardButton("📰 Upload Editorial")],
            ], resize_keyboard=True)
        else:
            # Members: only mini app button
            webapp_url = os.environ.get("A2Z_WEBAPP_URL", "https://your-miniapp-url.com")
            kb_member = [[InlineKeyboardButton("🚀 Open Mini App", url=webapp_url)]]
            reply_kb = None
            extra_info = "\n_Tap below to open the A2Z Mini App_"

    if admin:
        msg = (
            f"👋 *A2Z Admin Panel*\n\n"
            f"🎨 Rebrand Mock — Send .html to rebrand\n"
            f"📤 Upload Mock — Upload to vault\n"
            f"📰 Upload Editorial — Add study material\n"
            f"{access_line}{stat_line}"
        )
    else:
        msg = (
            f"👋 *Welcome to A2Z Updates4U!*\n\n"
            f"⚔️ Take mock tests, earn XP, and climb the ranks!\n"
            f"{access_line}{stat_line}"
            f"{fomo}"
            f"{extra_info}"
        )
        reply_kb = InlineKeyboardMarkup(kb_member)

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_kb,
    )


async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*A2Z Updates Bot*\n\n"
        "*Commands:*\n"
        "/start – Welcome + access check\n"
        "/help  – This text\n"
        "/dashboard – Your stats & access status\n"
        "/leaderboard – View leaderboard for a mock\n"
        "/invite – Get your invite link\n"
        "/verify – Verify pending invites\n\n"
        "*How to use:*\n"
        "1. Send any `.html` mock file\n"
        "2. Choose \"Rebrand Only\" or \"Rebrand + Rephrase\"\n"
        "3. Download your customised mock with unique ID\n"
        "4. Take the mock, submit results via the app\n"
        "5. Check /leaderboard for your rank\n\n"
        f"*Channel:* {CHANNEL_LINK}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Deep link handlers ──────────────────────────────────────────────────

async def _handle_submit_link(update: Update, deep_link: str):
    """Handle /start submit_MOCK-xxx_score_25_time_342_acc_83_qtimes_12-8-15..."""
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    try:
        parts = deep_link.replace("submit_", "").split("_")
        mock_id = parts[0]
        data = {}
        for p in parts[1:]:
            if "-" in p and not p.startswith("qtimes"):
                k, v = p.split("-", 1)
                data[k] = v
        score = int(data.get("score", 0))
        time_sec = float(data.get("time", 0))
        accuracy = float(data.get("acc", 0))
        correct = int(data.get("correct", 0))
        wrong = int(data.get("wrong", 0))
        skipped = int(data.get("skipped", 0))
        uname = update.effective_user.first_name or update.effective_user.username or str(uid)
        qtimes_idx = deep_link.find("qtimes_")
        qtimes_str = deep_link[qtimes_idx + 7:] if qtimes_idx >= 0 else ""
        attempt_id = start_attempt(uid, mock_id, uname)
        mock = get_mock(mock_id)
        questions = get_mock_questions(mock_id) if mock else []
        qtimes = []
        if qtimes_str:
            qtimes = [float(x) for x in qtimes_str.split("-") if x]
        for i, q in enumerate(questions):
            qt = qtimes[i] if i < len(qtimes) else 0.0
            save_response(attempt_id, uid, q["question_id"], q["q_number"], -1, 0, qt, 0)
        submit_attempt(attempt_id, score, correct, wrong, skipped, accuracy, time_sec, 0)
        increment_mock_attempts(mock_id)

        # Aggregate analytics from responses
        update_user_stats_after_attempt(uid, mock_id)

        # PvP Challenge: check if this user has pending challenges for this mock
        pending_ch = db_fetchall(
            "SELECT match_id FROM challenges WHERE mock_id = ? AND (challenger_id = ? OR rival_id = ?) AND status IN ('pending','accepted')",
            (mock_id, uid, uid),
        )
        for pc in (pending_ch or []):
            result = complete_challenge(pc["match_id"], uid, score, attempt_id)
            if result and result["status"] == "completed":
                # Send scorecard to both players
                c_uid = result["challenger_id"]
                r_uid = result["rival_id"]
                ch_name = db_fetchone("SELECT first_name FROM users WHERE telegram_id = ?", (c_uid,))
                ch_name = (ch_name["first_name"] if ch_name else "Challenger")[:15]
                rv_name = db_fetchone("SELECT first_name FROM users WHERE telegram_id = ?", (r_uid,))
                rv_name = (rv_name["first_name"] if rv_name else "Rival")[:15]
                winner_name = ch_name if result["winner_id"] == c_uid else rv_name
                scorecard = (
                    f"⚔️ *Head-to-Head Scorecard*\n\n"
                    f"🟦 {ch_name}: {result['challenger_score']}\n"
                    f"🟥 {rv_name}: {result['rival_score']}\n\n"
                    f"🏆 *Winner: {winner_name}* (+100 XP)"
                )
                for pid in [c_uid, r_uid]:
                    try:
                        await context.bot.send_message(pid, scorecard, parse_mode=ParseMode.MARKDOWN)
                        award_xp(db_execute, db_commit, result["winner_id"], 100,
                                 f"PvP victory — {pc['match_id']}", f"pvp_{pc['match_id']}")
                    except Exception:
                        pass
                # Lounge broadcast (GROWTH-05)
                lounge_id = os.environ.get("A2Z_LOUNGE_CHAT_ID", "")
                if lounge_id:
                    try:
                        await context.bot.send_message(
                            lounge_id,
                            f"🚨 *RIVALRY ALERT!*\n\n{scorecard}\n\n_Throttled: max 3/hr_",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    except Exception:
                        pass

        # AIR 209 Benchmark: if user beats benchmark, grant premium access
        benchmark = (mock["benchmark_score"] if mock else None)
        if benchmark and score >= benchmark:
            grant_premium_access(uid, 30, "paid")
            await update.message.reply_text(
                f"🎯 *BENCHMARK CRUSHED!*\n"
                f"You scored {score}/{benchmark} — beating the AIR 209 target!\n"
                f"🏆 30 days PREMIUM access UNLOCKED!",
                parse_mode=ParseMode.MARKDOWN,
            )

        # Study Trio: check if all 3 completed this mock
        check_trio_completion(uid, mock_id, context.bot)

        rank, total, percentile = get_user_rank(mock_id, attempt_id)

        # Auto-award XP for quiz performance
        xp_awarded = 0
        if GAME_OK and accuracy >= 80:
            xp_awarded = QUIZ_XP
            # Also complete daily quest if exists
            complete_daily_quest(db_execute, db_commit, uid)
            award_xp(db_execute, db_commit, uid, xp_awarded, f"Quiz >80% on {mock_id}")
        # Hidden quest: First Blood (100% on a mock)
        if GAME_OK and accuracy >= 100 and total <= 1:
            check_first_blood(db_execute, db_commit, mock_id, uid)
        # Raid boss damage
        if GAME_OK:
            deal_raid_damage(db_execute, db_commit, uid, 1, "mock_complete")

        # Referral verification: if this user was invited, verify the invite
        inviter_id = verify_referral_by_action(uid)
        if inviter_id and GAME_OK:
            award_xp(db_execute, db_commit, inviter_id, INVITE_XP,
                     "Referral verified — friend completed mock", f"invite_mock_{uid}_{mock_id}")
            try:
                await context.bot.send_message(
                    inviter_id,
                    f"🎯 *Referral Verified!*\n"
                    f"+{INVITE_XP} XP. Your friend just completed their first mock!\n"
                    f"Check /verify to see your invite status and unlock premium access.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass

        rank, total, percentile = get_user_rank(mock_id, attempt_id)
        user = db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (uid,)) if DB_OK else None
        new_rank_name = RANK_NAMES.get(user["rank"], "") if user and GAME_OK else ""

        await update.message.reply_text(
            f"🎯 *Result Submitted!*\n\n"
            f"*Mock:* {mock['title'] if mock else mock_id}\n"
            f"*Score:* {score}/{len(questions) if questions else '?'}\n"
            f"*Accuracy:* {accuracy}%\n"
            f"*Time:* {int(time_sec // 60)}m {int(time_sec % 60)}s\n\n"
            f"📊 *Rank:* #{rank} of {total}\n"
            f"📈 *Percentile:* {percentile}%\n"
            + (f"⚡ *+{xp_awarded} XP* earned! Rank: {new_rank_name}\n" if xp_awarded else "")
            + f"\nUse /leaderboard {mock_id} for full leaderboard",
            parse_mode=ParseMode.MARKDOWN,
        )
        if not has_free_access(uid)[0]:
            use_free_mock(uid)
    except Exception as e:
        log.exception("Submit link parse error")
        await update.message.reply_text(f"Error processing submission")


async def _handle_invite_link(update: Update, deep_link: str):
    if not DB_OK:
        return
    token = deep_link.replace("inv_", "")
    uid = update.effective_user.id
    record_invite_join(token, uid)
    await update.message.reply_text("Invite accepted! Welcome to A2Z Updates.\nUse /start to begin.")


# ═══════════════════════════════════════════════════════════════════════════
# AI INSIGHTS ENGINE  (PHASE 5B — Deterministic + Gemini Polish)
# ═══════════════════════════════════════════════════════════════════════════

def _classify_accuracy(acc: float) -> str:
    if acc >= 70: return "Strong"
    if acc >= 40: return "Moderate"
    return "Weak"


def _generate_insights_text(user_id: int) -> str:
    """Template-based Hinglish insights from analytics data. Falls back if no Gemini."""
    if not DB_OK:
        return "_Analytics not available._"
    subj = get_user_subject_summary(user_id) or []
    weak = get_user_weak_areas(user_id, min_attempts=2, top_n=4) or []
    silly = get_user_silly_mistakes(user_id, 3) or []
    if not subj and not weak:
        return "_Not enough data yet. Complete a few mocks to unlock AI insights._"

    lines = ["🤖 *AI Insights*", ""]
    # Subject overview
    if subj:
        strongest = max(subj, key=lambda x: x["accuracy"])
        weakest = min(subj, key=lambda x: x["accuracy"])
        lines.append(f"🟢 *Strongest:* {strongest['subject']} ({strongest['accuracy']}% accuracy)")
        lines.append(f"🔴 *Weakest:* {weakest['subject']} ({weakest['accuracy']}% — {weakest['attempts']} questions)")
        lines.append("")

    # Weak areas with Hinglish tips
    if weak:
        lines.append("*⚡ Priority Weak Areas:*")
        for w in weak[:3]:
            cls = _classify_accuracy(w["accuracy"])
            if cls == "Weak" and w["attempts"] >= 3:
                lines.append(f"• *{w['topic']}* ({w['chapter']}): sirf {w['accuracy']}% accuracy. "
                             f"Yahan conceptual clarity improve karo. {w['attempts']} sawaal kiye, {w['correct']} sahi.")
            elif cls == "Weak":
                lines.append(f"• *{w['topic']}* ({w['chapter']}): {w['accuracy']}% accuracy. "
                             f"Is topic pe focus badhao — abhi tak sirf {w['attempts']} sawaal kiye hain.")
            else:
                lines.append(f"• *{w['topic']}* ({w['chapter']}): {w['accuracy']}%. Room for improvement.")
        lines.append("")

    # Silly mistakes
    if silly:
        lines.append("*🤦 Silly Mistakes Detected:*")
        for s in silly:
            q_text = (s.get("text") or "")[:80].strip()
            lines.append(f"• Easy Q answered wrong: _{q_text}..._ ({s.get('mock_title','Mock')})")
        lines.append("_Tip: Easy sawaalon me jaldbaazi na karein. Double-check before moving on._")
        lines.append("")

    # Time management tip
    lines.append("*⏱️ Time Strategy:*")
    lines.append("Pehle easy sawaal karo, phir medium, last me hard. Agar koi sawaal 2 min se zyada lag raha hai — skip karo aur baad me aao.")
    return "\n".join(lines)


async def _generate_gemini_insights(user_id: int) -> Optional[str]:
    """Use Gemini to generate Hinglish coaching text from analytics JSON."""
    if not DB_OK:
        return None
    subj = get_user_subject_summary(user_id) or []
    weak = get_user_weak_areas(user_id, top_n=5) or []
    trend = get_user_score_trend(user_id, 8) or []
    if not subj:
        return None
    payload = {
        "subjects": [dict(s) for s in subj],
        "weak_areas": [dict(w) for w in weak],
        "recent_trend": [{"title": t["mock_title"], "score": t["total_score"], "accuracy": t["accuracy"]} for t in trend],
    }
    prompt = (
        "You are an exam performance coach for SSC/RRB students. Based on this analytics JSON, "
        "write 3-4 lines of personalized feedback in Hinglish. Focus on weakest topics first, "
        "then time management tip. Be encouraging but direct. Keep it under 500 chars.\n\n"
        f"JSON: {json.dumps(payload)}"
    )
    try:
        result = await _gemini_call(prompt, GEMINI_MODEL, max_retries=2)
        result = result.strip()
        if result and len(result) > 10:
            return f"🤖 *AI Coach says:*\n{result[:800]}"
    except Exception:
        pass
    return None


def _generate_ai_mock_analysis(user_id: int, mock_id: str) -> str:
    """Deterministic mock-level analysis: errors, speed, weak areas."""
    attempt = db_fetchone(
        "SELECT * FROM attempts WHERE user_id = ? AND mock_id = ? ORDER BY submitted_at DESC LIMIT 1",
        (user_id, mock_id),
    )
    if not attempt:
        return "_Attempt data not found._"

    mock = get_mock(mock_id)
    title = (mock["title"] if mock else mock_id)[:40]
    acc = attempt["accuracy"]
    score = attempt["total_score"]
    correct = attempt["correct_count"]
    wrong = attempt["wrong_count"]
    skipped = attempt["skipped_count"]
    time_sec = attempt["total_time_sec"] or 0

    # Classification
    perf_label = "Excellent" if acc >= 85 else ("Good" if acc >= 65 else ("Average" if acc >= 45 else "Needs Work"))
    emoji = "🔥" if acc >= 85 else ("✅" if acc >= 65 else ("⚠️" if acc >= 45 else "❌"))

    # Speed analysis
    total_q = correct + wrong + skipped
    avg_time = round(time_sec / total_q, 1) if total_q > 0 else 0
    speed_label = "Too fast" if avg_time < 20 else ("Ideal" if avg_time < 60 else "Slow")

    # Silly mistakes from this mock
    silly = db_fetchall(
        """SELECT q.text, q.q_number FROM responses r
           JOIN questions q ON r.question_id = q.question_id
           WHERE r.user_id = ? AND r.attempt_id = ? AND r.is_correct = 0 AND q.difficulty_level = 'easy'""",
        (user_id, attempt["attempt_id"]),
    ) or []

    lines = [
        f"{emoji} *Mock Analysis: {title}*",
        f"",
        f"📊 Score: {score} | Accuracy: {acc}% | *{perf_label}*",
        f"✅ Correct: {correct} | ❌ Wrong: {wrong} | ⏭️ Skipped: {skipped}",
        f"⏱️ Avg time/Q: {avg_time}s — *{speed_label}*",
    ]

    if silly:
        lines.append(f"")
        lines.append(f"🤦 *{len(silly)} silly mistakes* (easy Qs answered wrong):")
        for s in silly[:3]:
            lines.append(f"  • Q{s['q_number']}: _{ (s['text'] or '')[:60] }..._")

    # Weak topics in this mock
    topic_q = db_fetchall(
        """SELECT t.name as topic, COUNT(*) as total, SUM(r.is_correct) as correct
           FROM responses r JOIN questions q ON r.question_id = q.question_id
           LEFT JOIN topics t ON q.topic_id = t.id
           WHERE r.user_id = ? AND r.attempt_id = ? AND q.topic_id IS NOT NULL
           GROUP BY q.topic_id HAVING SUM(r.is_correct) * 1.0 / COUNT(*) < 0.5
           ORDER BY total DESC LIMIT 3""",
        (user_id, attempt["attempt_id"]),
    ) or []
    if topic_q:
        lines.append(f"")
        lines.append(f"⚡ *Topics to improve:*")
        for t in topic_q:
            t_acc = round((t["correct"] / t["total"]) * 100, 1) if t["total"] > 0 else 0
            lines.append(f"  • {t['topic']}: {t['correct']}/{t['total']} ({t_acc}%)")

    # Tips
    lines.append(f"")
    if skipped > 3:
        lines.append("💡 *Tip:* Zyada skip mat karo — attempted questions me accuracy badhao.")
    if avg_time < 15:
        lines.append("💡 *Tip:* Bahut tez ho — thoda slow karo, accuracy badhegi.")
    elif avg_time > 90:
        lines.append("💡 *Tip:* Speed badhao. Easy questions 30-45 sec me khatam karo.")

    return "\n".join(lines)


# ── Command handlers ─────────────────────────────────────────────────────

async def _dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    get_or_create_user(uid, update.effective_user.username or "", update.effective_user.first_name or "")
    has_access, days_left, free_left = has_free_access(uid)
    invites = get_monthly_invite_count(uid)
    stats = get_user_stats(uid)
    attempts = get_user_attempts(uid, 5)
    msg = "📊 *A2Z Dashboard*\n\n"
    if has_access:
        msg += f"🎫 *Premium Access:* {days_left} days remaining\n"
    else:
        msg += f"⚠️ *Free Tier:* {free_left} mocks remaining\n"
    msg += f"👥 *Invites this month:* {invites}/3\n\n"
    if stats:
        msg += (f"📝 *Total mocks:* {stats.get('total_mocks', 0)}\n"
                f"🎯 *Best score:* {stats.get('best_score', 0)}\n"
                f"📈 *Avg accuracy:* {stats.get('avg_accuracy', 0):.1f}%\n\n")
    if attempts:
        msg += "*Recent attempts:*\n"
        for a in attempts[:5]:
            mtitle = a.get("mock_title", a["mock_id"])[:30]
            msg += f"• {mtitle} — {a['total_score']}/{a['correct_count'] + a['wrong_count'] + a['skipped_count']} ({a['accuracy']:.0f}%)\n"
    kb = [[InlineKeyboardButton("👥 Get Invite Link", callback_data="cmd:invite"),
           InlineKeyboardButton("✅ Verify Invites", callback_data="cmd:verify")]]
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


async def _leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    args = context.args
    if not args:
        mocks = list_mocks(5)
        if not mocks:
            await update.message.reply_text("No mocks available yet.")
            return
        msg = "*Select a mock for leaderboard:*\n"
        kb = []
        for m in mocks:
            kb.append([InlineKeyboardButton(f"🏆 {m['title'][:40]}", callback_data=f"lb:{m['mock_id']}")])
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))
        return
    mock_id = args[0]
    mock = get_mock(mock_id)
    if not mock:
        await update.message.reply_text("Mock not found.")
        return
    lb = get_leaderboard(mock_id, 20)
    stats = get_mock_stats(mock_id)
    msg = f"🏆 *{mock['title']}*\n"
    if stats:
        msg += f"Attempts: {stats.get('total_attempts', 0)} | Avg: {stats.get('avg_score', 0)} | Best: {stats.get('best_score', 0)}\n\n"
    if not lb:
        msg += "_No attempts yet._"
    else:
        for r in lb[:15]:
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"], f"#{r['rank']}")
            msg += f"{medal} {r['name'][:15]} — {r['score']}/{mock['question_count']} ({r['accuracy']}%) {r['time_sec']}s\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def _invite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    token = create_invite(uid)
    bot_username = context.bot.username
    invite_link = f"https://t.me/{bot_username}?start=inv_{token}"
    count = get_monthly_invite_count(uid)
    await update.message.reply_text(
        f"👥 *Your Invite Link*\n\n"
        f"Share this link with friends:\n"
        f"`{invite_link}`\n\n"
        f"📊 Verified: {count}/3 this month\n"
        f"Unlock: 30 days free unlimited access\n\n"
        f"_They must join @A2Zupdates4U for verification._\n"
        f"After they join via your link, use /verify to check.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    status_msg = await update.message.reply_text("⏳ Verifying channel memberships...")
    has_access, msg = check_and_grant_access(uid, CHANNEL_ID, BOT_TOKEN)

    if GAME_OK and has_access:
        verified_count = get_monthly_invite_count(uid)
        xp_earned = verified_count * INVITE_XP
        if xp_earned > 0:
            award_xp(db_execute, db_commit, uid, xp_earned, "Verified Invites")
            msg += f"\n\n*+{xp_earned} XP* from verified invites!"

    await status_msg.edit_text(msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Dashboard", callback_data="cmd:dashboard")]]))


# ═══════════════════════════════════════════════════════════════════════════
# GAMIFICATION COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

async def _mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hunter License — RPG style stats card."""
    if not DB_OK or not GAME_OK:
        await update.message.reply_text("Gamification system offline.")
        return
    uid = update.effective_user.id
    user = db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (uid,))
    if not user:
        await update.message.reply_text("Start the bot first with /start")
        return

    # Apply decay on check
    decayed, lost = apply_rank_decay(db_execute, db_commit, uid)
    user = db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (uid,))

    html_card = hunter_license_html(dict(user))
    # Send as HTML file
    import tempfile
    tf = tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False)
    tf.write(html_card)
    tpath = tf.name
    tf.close()

    decay_msg = f"\nYour rank decayed -{lost} XP due to inactivity." if decayed else ""
    await update.message.reply_text(
        "⚔️ *HUNTER LICENSE*" + decay_msg,
        parse_mode=ParseMode.MARKDOWN,
    )
    with open(tpath, "rb") as f:
        await update.message.reply_document(f, filename="Hunter_License.html")
    os.unlink(tpath)


async def _guild_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_OK or not GAME_OK:
        await update.message.reply_text("Gamification system offline.")
        return
    uid = update.effective_user.id
    args = context.args

    if not args:
        info = get_guild_info(db_execute, uid)
        if info:
            members_str = "\n".join(
                f"{'✅' if m['quest_done_today'] else '❌'} {m.get('first_name', m.get('username', str(m['telegram_id'])))} — {m['xp']} XP [{RANK_NAMES.get(m['rank'], 'E')}]"
                for m in info["members"]
            )
            await update.message.reply_text(
                f"⚔️ *Guild: {info['name']}*\n"
                f"Multiplier: {info['multiplier']}x\n\n"
                f"*Members:*\n{members_str}\n\n"
                f"_All members must complete daily quest for 1.5x multiplier._\n"
                f"Commands: /guild create NAME | /guild join GUILD_ID | /guild leave",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(
                "You are not in a guild.\n\n"
                "/guild create NAME — Create a guild\n"
                "/guild join GUILD_ID — Join an existing guild"
            )
        return

    action = args[0].lower()
    if action == "create" and len(args) >= 2:
        name = " ".join(args[1:])
        ok, result = create_guild(db_execute, db_commit, uid, name)
        await update.message.reply_text(
            f"⚔️ Guild *{name}* created!\nShare ID: `{result}`" if ok else f"Failed: {result}",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif action == "join" and len(args) >= 2:
        guild_id = args[1]
        ok, result = join_guild(db_execute, db_commit, uid, guild_id)
        await update.message.reply_text(result)
    elif action == "leave":
        leave_guild(db_execute, db_commit, uid)
        await update.message.reply_text("You left the guild.")
    else:
        await update.message.reply_text("Usage: /guild create NAME | /guild join ID | /guild leave")


async def _access_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's access tier, invites, and days remaining."""
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    get_or_create_user(uid, update.effective_user.username or "", update.effective_user.first_name or "")
    user = db_fetchone("SELECT premium_tier, free_access_expiry, premium_access_expiry FROM users WHERE telegram_id = ?", (uid,))
    has_access, days_left, free_left = has_free_access(uid)
    verified = get_monthly_invite_count(uid)
    action_verified = get_monthly_action_verified_count(uid)
    tier = (user["premium_tier"] if user else "free") or "free"
    tier_names = {"free": "Free Tier", "tier1": "Tier 1 (15d)", "tier2": "Tier 2 (30d)", "paid": "Paid (Premium)"}
    msg = (
        f"🔑 *Access Status*\n\n"
        f"🎫 Tier: *{tier_names.get(tier, tier)}*\n"
        f"{'✅' if has_access else '⚠️'} Status: {'Active — ' + str(days_left) + ' days left' if has_access else 'No active access'}\n"
        f"📝 Free mocks left: {free_left}\n"
        f"👥 Verified invites: {verified} (this month)\n"
        f"🎯 Action-verified: {action_verified}\n\n"
    )
    if not has_access and verified < 3:
        msg += f"🔗 Share your invite link to unlock access: /invite\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════════════════════════════════════
# PvP CHALLENGE  (GROWTH-03)
# ═══════════════════════════════════════════════════════════════════════════

async def _challenge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a PvP challenge after mock submission."""
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    args = context.args
    if not args:
        # List pending challenges
        ch = db_fetchall(
            "SELECT * FROM challenges WHERE (challenger_id = ? OR rival_id = ?) AND status != 'completed' ORDER BY created_at DESC LIMIT 5",
            (uid, uid),
        )
        if not ch:
            await update.message.reply_text("No active challenges.\nUse /challenge <mock_id> to start one.")
            return
        lines = ["⚔️ *Active Challenges*", ""]
        for c in ch:
            status = "⏳ Pending" if c["status"] == "pending" else "🔄 Accepted"
            mock = get_mock(c["mock_id"])
            mtitle = (mock["title"] if mock else c["mock_id"])[:25]
            lines.append(f"{status} *{mtitle}*\n  Challenger score: {c.get('challenger_score','-')}\n  Link: `{c['match_id']}`")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        return

    mock_id = args[0]
    mock = get_mock(mock_id)
    if not mock:
        await update.message.reply_text("Mock not found. Use a valid mock_id.")
        return
    match_id = create_challenge(uid, mock_id)
    deep_link = f"https://t.me/A2ZUpdatesBot?start=challenge_{match_id}"
    await update.message.reply_text(
        f"⚔️ *Challenge Created!*\n\n"
        f"Mock: *{mock['title']}*\n"
        f"Share this link:\n`{deep_link}`\n\n"
        f"_Your rival must open this link, take the same mock, and submit results._",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _handle_challenge_link(update: Update, deep_link: str):
    """Handle /start challenge_MATCHID deep link."""
    if not DB_OK:
        return
    match_id = deep_link.replace("challenge_", "")
    uid = update.effective_user.id
    ch = accept_challenge(match_id, uid)
    if not ch:
        await update.message.reply_text("⚠️ Challenge not found or already accepted.")
        return
    mock = get_mock(ch["mock_id"])
    uname = update.effective_user.first_name or "Aspirant"
    await update.message.reply_text(
        f"⚔️ *Challenge Accepted!*\n\n"
        f"Mock: *{mock['title'] if mock else ch['mock_id']}*\n"
        f"Challenger: {uname}\n\n"
        f"_Now take the mock from the menu button and submit your results._\n"
        f"_The bot will auto-compare scores._",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _raid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin creates a raid boss, or users can check active raid status."""
    if not DB_OK or not GAME_OK:
        await update.message.reply_text("Game system offline.")
        return
    uid = update.effective_user.id
    args = context.args

    if not args or args[0].lower() == "status":
        active = get_active_raid(db_execute)
        if not active:
            await update.message.reply_text("No active raid. Admins can create one with /raid create.")
            return
        await update.message.reply_text(
            f"🚨 *Raid Boss: {active['boss_name']}*\n"
            f"❤️ HP: {active['hp_current']}/{active['hp_total']}\n"
            f"🏆 Reward: {active['reward']}\n"
            f"⏰ Deadline: {active['deadline']}\n\n"
            f"_Every quiz complete & new user join deals 1 damage!_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    sub = args[0].lower()
    if sub == "create" and is_admin(uid):
        if len(args) < 4:
            await update.message.reply_text("/raid create <name> <hp> <reward>")
            return
        name = args[1]
        hp = int(args[2])
        reward = " ".join(args[3:])
        raid_id = create_raid(db_execute, db_commit, name, hp, 72, reward)
        await update.message.reply_text(
            f"🚨 *RAID EVENT LIVE!*\n\n"
            f"Boss: {name} | HP: {hp}\n"
            f"Reward: {reward}\n"
            f"Raid ID: `{raid_id}`\n\n"
            f"_Every quiz complete deals 1 damage!_",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("Use /raid to check status.\nAdmins: /raid create <name> <hp> <reward>")


def inject_editorial_tracker(html: str, editorial_id: str) -> str:
    """Inject results tracker + mobile-friendly CSS into editorial HTML.
    Keeps original structure intact. Adds:
      - Floating bottom bar with live score counter
      - Required viewport meta for mini-app
      - Telegram WebApp script for sendData
      - Submit button that reports cloze + jumble results to bot
    """
    tracker_css = """
    /* A2Z Results Tracker — injected */
    :root{--tracker-bg:#1a1a2e;--tracker-accent:#9d8fff;--tracker-green:#22c55e;--tracker-gold:#fbbf24;--tracker-text:#fff}
    .a2z-tracker{position:fixed;bottom:0;left:0;right:0;background:var(--tracker-bg);
      padding:10px 14px;display:flex;align-items:center;justify-content:space-between;
      z-index:9999;box-shadow:0 -2px 12px rgba(0,0,0,.4);font-family:Inter,sans-serif;
      padding-bottom:max(10px,env(safe-area-inset-bottom));}
    .a2z-tracker .a2z-score{display:flex;gap:10px;font-size:.72rem;color:#94a3b8;}
    .a2z-tracker .a2z-score span{color:var(--tracker-gold);font-weight:700;}
    .a2z-tracker .a2z-btn{background:var(--tracker-accent);color:#fff;border:none;
      padding:8px 20px;border-radius:8px;font-weight:700;font-size:.8rem;cursor:pointer;}
    .a2z-tracker .a2z-btn.done{background:var(--tracker-green);}
    .a2z-toast{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#1a1a2e;
      color:#fff;padding:16px 24px;border-radius:12px;z-index:9999;font-family:Inter,sans-serif;
      text-align:center;display:none;box-shadow:0 8px 32px rgba(0,0,0,.5);}
    body.a2z-mode{padding-bottom:80px !important;}
    @media(max-width:600px){
      .a2z-tracker .a2z-score{font-size:.68rem;gap:6px;}
      .a2z-tracker .a2z-btn{font-size:.75rem;padding:8px 14px;}
    }
    """
    tracker_js = """
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script>
    (function(){
      var tg = window.Telegram?.WebApp;
      var scores = {clozeTotal:0,clozeCorrect:0,jumbleTotal:0,jumbleCorrect:0,submitted:false};
      var editorialId = 'EDITORIAL_ID_PLACEHOLDER';

      // Count total questions on page load
      scores.clozeTotal = document.querySelectorAll('.mcq-opts').length;
      scores.jumbleTotal = document.querySelectorAll('.pj-opts').length;

      // Override clozeAns to track correct answers
      var origCloze = window.clozeAns;
      window.clozeAns = function(btn) {
        var parent = btn.closest('.mcq-opts');
        if (parent && parent.querySelector('.correct,.wrong')) return;
        var correct = btn.dataset.ans;
        if (btn.textContent.trim() === correct) scores.clozeCorrect++;
        origCloze(btn);
        updateTracker();
      };

      // Override pjAns to track correct answers
      var origPj = window.pjAns;
      window.pjAns = function(btn) {
        var correctIdx = parseInt(btn.dataset.ans);
        var myIdx = parseInt(btn.dataset.idx);
        if (myIdx === correctIdx) scores.jumbleCorrect++;
        origPj(btn);
        updateTracker();
      };

      function updateTracker() {
        var el = document.getElementById('a2z-score-display');
        if (!el) return;
        var total = scores.clozeTotal + scores.jumbleTotal;
        var correct = scores.clozeCorrect + scores.jumbleCorrect;
        el.innerHTML = '<span>Cloze:'+scores.clozeCorrect+'/'+scores.clozeTotal+'</span>'+
                       '<span>Jumble:'+scores.jumbleCorrect+'/'+scores.jumbleTotal+'</span>'+
                       '<span>Total: <b style="color:var(--tracker-gold)">'+correct+'/'+total+'</b></span>';
      }

      function submitResults() {
        if (scores.submitted) return;
        scores.submitted = true;
        var total = scores.clozeTotal + scores.jumbleTotal;
        var correct = scores.clozeCorrect + scores.jumbleCorrect;
        var acc = total > 0 ? Math.round(correct/total*100) : 0;
        document.getElementById('a2z-submit-btn').textContent = 'Submitted';
        document.getElementById('a2z-submit-btn').classList.add('done');
        document.getElementById('a2z-toast').style.display='block';
        document.getElementById('a2z-toast').innerHTML =
          '<div style="font-size:2rem;">'+(acc>=70?'🎉':acc>=40?'✅':'📚')+'</div>'+
          '<div style="font-weight:700;margin:8px 0;">'+correct+'/'+total+' correct ('+acc+'%)</div>'+
          '<div style="font-size:.75rem;color:#94a3b8;">Results saved! Check Analytics tab.</div>';
        setTimeout(function(){document.getElementById('a2z-toast').style.display='none';},3000);

        if (tg) {
          tg.sendData(JSON.stringify({action:'editorial_result',editorial_id:editorialId,
            cloze_correct:scores.clozeCorrect,cloze_total:scores.clozeTotal,
            jumble_correct:scores.jumbleCorrect,jumble_total:scores.jumbleTotal}));
        }
      }

      // Build tracker UI
      var tracker = document.createElement('div');
      tracker.className = 'a2z-tracker';
      tracker.id = 'a2z-tracker';
      tracker.innerHTML = '<div class="a2z-score" id="a2z-score-display">'+
        '<span>Cloze:0/'+scores.clozeTotal+'</span>'+
        '<span>Jumble:0/'+scores.jumbleTotal+'</span>'+
        '<span>Total: <b style="color:var(--tracker-gold)">0/'+(scores.clozeTotal+scores.jumbleTotal)+'</b></span>'+
        '</div>'+
        '<button class="a2z-btn" id="a2z-submit-btn" onclick="submitResults()">Submit</button>';
      document.body.appendChild(tracker);

      // Toast
      var toast = document.createElement('div');
      toast.className = 'a2z-toast';
      toast.id = 'a2z-toast';
      document.body.appendChild(toast);

      // Add bottom padding for tracker
      document.body.classList.add('a2z-mode');
    })();
    </script>
    """
    # Inject CSS into <head> before </style>
    if '</style>' in html:
        html = html.replace('</style>', tracker_css + '\n</style>')
    else:
        html = html.replace('<head>', '<head>\n<style>' + tracker_css + '</style>')

    # Replace placeholder with actual editorial ID
    tracker_js = tracker_js.replace('EDITORIAL_ID_PLACEHOLDER', editorial_id)

    # Inject JS before </body>
    if '</body>' in html:
        html = html.replace('</body>', tracker_js + '\n</body>')
    else:
        html += tracker_js

    return html


async def _editorial_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View or upload editorials. Admins can generate vocab quiz from editorial."""
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    args = context.args
    if args and args[0] == "upload":
        await update.message.reply_text("Send me the editorial .html file.")
        return
    if args and len(args[0]) > 3:
        # Treat as editorial ID — send the file
        ed_id = args[0]
        ed = db_fetchone("SELECT * FROM editorials WHERE editorial_id = ?", (ed_id,))
        if not ed:
            await update.message.reply_text("Editorial not found.")
            return
        store_path = Path(__file__).parent / "mocks_storage" / f"{ed_id}.html"
        orig_path = Path(__file__).parent / (ed.get("filename") or "")
        src = store_path if store_path.exists() else orig_path
        if src and src.exists():
            html = src.read_text(encoding="utf-8")
            if 'a2z-tracker' not in html:
                html = inject_editorial_tracker(html, ed_id)
                store_path.write_text(html, encoding="utf-8")
            import tempfile as t2
            tf = t2.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False)
            tf.write(html); tpath = tf.name; tf.close()
            with open(tpath, "rb") as f:
                await update.message.reply_document(f, filename=f"Editorial_{ed['title'][:30]}.html",
                    caption=f"📰 *{ed['title'][:60]}*\n\nOpen to study. Submit results via the tracker!",
                    parse_mode=ParseMode.MARKDOWN)
            os.unlink(tpath)
            return
    editorials = list_editorials(10)
    if not editorials:
        await update.message.reply_text("No editorials yet. Admins can upload .html files.")
        return
    lines = ["📰 *Recent Editorials*", ""]
    for e in editorials:
        lines.append(f"• *{e['title'][:50]}* — {e.get('article_date','')[:10]}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def _generate_editorial_quiz(admin_id: int, editorial: dict) -> Optional[str]:
    """Use Gemini to generate a 5-question vocab/cloze quiz from editorial content."""
    # Load editorial HTML and extract text
    store_path = Path(__file__).parent / "mocks_storage" / f"{editorial['editorial_id']}.html"
    if not store_path.exists():
        return None
    try:
        html = store_path.read_text(encoding="utf-8")[:8000]
        prompt = (
            "From this editorial content, extract the 5 most important vocabulary words. "
            "For each word, create a multiple-choice question asking its meaning, with 4 options each. "
            "Return ONLY valid JSON: {\"title\": \"Editorial Vocab Quiz\", \"questions\": [ "
            "{\"text\": \"Meaning of 'WORD'?\", \"text_hi\": \"'WORD' का अर्थ?\", "
            "\"options\": [\"A\", \"B\", \"C\", \"D\"], \"options_hi\": [\"A\", \"B\", \"C\", \"D\"], "
            "\"correctIndex\": 0, \"explanation\": \"Meaning in English\", \"explanation_hi\": \"Hindi meaning\"}, ...]}"
            f"\n\nEditorial content:\n{html}"
        )
        result = await _gemini_call(prompt, GEMINI_MODEL, max_retries=2)
        data = json.loads(result)
        questions = data.get("questions", [])
        if len(questions) < 3:
            return None
        # Register as a mock
        title = data.get("title", "Editorial Vocab Quiz")[:60]
        mock_id = register_mock(admin_id, title, topic="Vocabulary", section="Editorial",
                                source_file=f"editorial_quiz_{editorial['editorial_id']}",
                                question_count=len(questions), timer_minutes=5)
        register_questions(mock_id, questions)
        return mock_id
    except Exception as e:
        log.warning("Editorial quiz generation failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD  (ADMIN-01 through ADMIN-04)
# ═══════════════════════════════════════════════════════════════════════════

async def _admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🔒 Admin only.")
        return

    args = context.args
    sub = (args[0].lower() if args else "overview")
    log_admin_action(uid, f"admin:{sub}", detail=" ".join(args[1:]) if len(args) > 1 else "")

    if sub == "overview":
        await _admin_overview(update)
    elif sub == "users":
        await _admin_users(update, args[1:] if len(args) > 1 else [])
    elif sub == "mocks":
        await _admin_mocks(update)
    elif sub == "user" and len(args) >= 2:
        try:
            target = int(args[1])
            await _admin_user_detail(update, target)
        except ValueError:
            await update.message.reply_text("Usage: /admin user <telegram_id>")
    elif sub == "invites":
        await _admin_invites(update)
    elif sub == "broadcast" and len(args) >= 2:
        msg_text = " ".join(args[1:])
        await _admin_broadcast(update, context, msg_text)
    elif sub == "add" and len(args) >= 2:
        try:
            new_admin = int(args[1])
            add_admin(new_admin, uid)
            get_or_create_user(new_admin)
            await update.message.reply_text(f"✅ User {new_admin} promoted to admin.")
            log_admin_action(uid, "admin:add", target_id=new_admin)
        except ValueError:
            await update.message.reply_text("Usage: /admin add <telegram_id>")
    elif sub == "export_users":
        await _admin_export_users(update)
    elif sub == "export_mocks":
        await _admin_export_mocks(update)
    elif sub == "backup":
        await _admin_backup(update)
    elif sub == "pay" and len(args) >= 3:
        try:
            puser_id = int(args[1])
            pdays = int(args[2])
            get_or_create_user(puser_id)
            grant_premium_access(puser_id, pdays, "paid")
            await update.message.reply_text(f"✅ User {puser_id} granted PAID access for {pdays} days.")
            log_admin_action(uid, "admin:pay", target_id=puser_id, detail=f"{pdays}d")
        except ValueError:
            await update.message.reply_text("Usage: /admin pay <user_id> <days>")
    elif sub == "set_benchmark" and len(args) >= 3:
        try:
            bmock_id = args[1]
            bscore = int(args[2])
            mock = get_mock(bmock_id)
            if not mock:
                await update.message.reply_text("Mock not found.")
            else:
                db_execute("UPDATE mocks SET benchmark_score = ? WHERE mock_id = ?", (bscore, bmock_id))
                db_commit()
                await update.message.reply_text(f"✅ Benchmark for {mock['title'][:30]}: {bscore}")
                log_admin_action(uid, "admin:set_benchmark", detail=f"{bmock_id}={bscore}")
        except ValueError:
            await update.message.reply_text("Usage: /admin set_benchmark <mock_id> <score>")
    elif sub == "schedule" and len(args) >= 3:
        smock_id = args[1]
        sdate = args[2]
        mock = get_mock(smock_id)
        if not mock:
            await update.message.reply_text("Mock not found.")
        else:
            db_execute("UPDATE mocks SET active_at = ?, scheduled_at = ? WHERE mock_id = ?",
                       (sdate, sdate, smock_id))
            db_commit()
            await update.message.reply_text(f"📅 {mock['title'][:30]} scheduled for {sdate}")
            log_admin_action(uid, "admin:schedule", detail=f"{smock_id}={sdate}")
    else:
        await update.message.reply_text(
            "*Admin Commands:*\n"
            "/admin overview — Dashboard overview\n"
            "/admin users — List all users\n"
            "/admin mocks — List all mocks\n"
            "/admin user <id> — Deep view of one user\n"
            "/admin invites — Invite network\n"
            "/admin broadcast <msg> — Send to all users\n"
            "/admin add <id> — Promote admin\n"
            "/admin export_users — CSV export users\n"
            "/admin export_mocks — CSV export mocks",
            parse_mode=ParseMode.MARKDOWN,
        )


async def _admin_users(update: Update, extra_args: list):
    limit = 30
    if extra_args:
        try:
            limit = int(extra_args[0])
        except ValueError:
            pass
    users = get_admin_users_list(limit)
    if not users:
        await update.message.reply_text("No users found.")
        return
    lines = [f"👥 *Users ({len(users)})*", ""]
    for u in users:
        name = (u["first_name"] or u["username"] or str(u["telegram_id"]))[:15]
        access = "✅" if u.get("free_access_expiry") else "⬜"
        lines.append(
            f"`{u['telegram_id']}` {name} | {u['xp']}XP {u['rank']} | "
            f"{u['mocks_taken']}m | {u['invites_sent']}inv {access}"
        )
    await update.message.reply_text("\n".join(lines[:60]), parse_mode=ParseMode.MARKDOWN)


async def _admin_mocks(update: Update):
    mocks = get_admin_mocks_list(50)
    if not mocks:
        await update.message.reply_text("No mocks registered.")
        return
    lines = [f"📝 *Mocks ({len(mocks)})*", ""]
    for m in mocks:
        lines.append(
            f"`{m['mock_id']}` {m['title'][:30]} | "
            f"{m['question_count']}Q | "
            f"{m.get('actual_attempts',0)} attempts | "
            f"Avg: {m.get('avg_score','-')}/{m.get('avg_accuracy','-')}%"
        )
    await update.message.reply_text("\n".join(lines[:60]), parse_mode=ParseMode.MARKDOWN)


async def _admin_user_detail(update: Update, target_id: int):
    data = get_user_deep_stats(target_id)
    if not data:
        await update.message.reply_text("User not found.")
        return
    u = data["user"]
    inv_by = data.get("invited_by")
    name = (u.get("first_name") or u.get("username") or str(target_id))
    msg = (
        f"🔍 *User: {name}*\n"
        f"ID: `{target_id}`\n"
        f"XP: {u.get('xp',0)} | Rank: {u.get('rank','E')}\n"
        f"Access: {u.get('free_access_expiry') or 'None'}\n"
        f"Invited by: {inv_by.get('first_name','None') if inv_by else 'None'}\n\n"
    )
    # Attempts
    attempts = data.get("attempts", [])
    if attempts:
        msg += f"*Recent attempts ({len(attempts)}):*\n"
        for a in attempts[:10]:
            mt = (a.get("mock_title") or a["mock_id"])[:20]
            msg += f"• {mt}: {a['total_score']}/{a['correct_count']+a['wrong_count']+a['skipped_count']} ({a['accuracy']:.0f}%)\n"
    # Invites sent
    inv_sent = data.get("invites_sent", [])
    if inv_sent:
        msg += f"\n*Invites sent ({len(inv_sent)}):*\n"
        for iv in inv_sent[:10]:
            iverified = "✅" if iv.get("channel_verified") else "⬜"
            iname = iv.get("invited_name") or iv.get("invited_username") or "?"
            msg += f"• {iname} {iverified}\n"
    await update.message.reply_text(msg[:4000], parse_mode=ParseMode.MARKDOWN)


async def _admin_invites(update: Update):
    net = get_admin_invite_network(30)
    if not net:
        await update.message.reply_text("No invite data.")
        return
    lines = [f"🔗 *Invite Leaderboard*", ""]
    for r in net:
        lines.append(
            f"{r['inviter_name'][:15]}: {r['total_invites']} total "
            f"({r['verified']}✅ {r['unverified']}⬜)"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def _admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    ids = get_admin_all_user_ids()
    success = 0
    fail = 0
    for tid in ids:
        try:
            await context.bot.send_message(tid, f"📢 *A2Z Broadcast*\n\n{text}", parse_mode=ParseMode.MARKDOWN)
            success += 1
        except Exception:
            fail += 1
    await update.message.reply_text(f"📢 Broadcast sent: {success} ok, {fail} failed (out of {len(ids)})")


async def _admin_export_users(update: Update):
    users = get_admin_users_list(1000)
    if not users:
        await update.message.reply_text("No users.")
        return
    lines = ["id,name,username,xp,rank,access,mocks,invites"]
    for u in users:
        name = (u.get("first_name") or "").replace(",", " ")
        uname = (u.get("username") or "").replace(",", " ")
        lines.append(f"{u['telegram_id']},{name},{uname},{u.get('xp',0)},{u.get('rank','E')},{u.get('free_access_expiry') or ''},{u.get('mocks_taken',0)},{u.get('invites_sent',0)}")
    import tempfile
    tf = tempfile.NamedTemporaryFile(suffix=".csv", mode="w", encoding="utf-8", delete=False)
    tf.write("\n".join(lines)); tpath = tf.name; tf.close()
    with open(tpath, "rb") as f:
        await update.message.reply_document(f, filename="users_export.csv")
    os.unlink(tpath)


async def _admin_export_mocks(update: Update):
    mocks = get_admin_mocks_list(1000)
    if not mocks:
        await update.message.reply_text("No mocks.")
        return
    lines = ["mock_id,title,section,q_count,attempts,avg_score,avg_accuracy,created"]
    for m in mocks:
        title = (m.get("title") or "").replace(",", " ")
        lines.append(f"{m['mock_id']},{title},{m.get('section','')},{m.get('question_count',0)},{m.get('actual_attempts',0)},{m.get('avg_score','-')},{m.get('avg_accuracy','-')},{m.get('created_at','')}")
    import tempfile
    tf = tempfile.NamedTemporaryFile(suffix=".csv", mode="w", encoding="utf-8", delete=False)
    tf.write("\n".join(lines)); tpath = tf.name; tf.close()
    with open(tpath, "rb") as f:
        await update.message.reply_document(f, filename="mocks_export.csv")
    os.unlink(tpath)


async def _admin_backup(update: Update):
    """Export all tables as JSON dump."""
    tables = db_fetchall("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    dump = {}
    for t in tables:
        tname = t["name"]
        rows = db_fetchall(f"SELECT * FROM {tname}")
        dump[tname] = [dict(r) for r in (rows or [])]
    import tempfile
    tf = tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False)
    json.dump(dump, tf, indent=2, default=str)
    tpath = tf.name; tf.close()
    with open(tpath, "rb") as f:
        await update.message.reply_document(f, filename=f"a2z_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    os.unlink(tpath)


# ═══════════════════════════════════════════════════════════════════════════
# FILE HANDLER (Admin-only) + KEYBOARD HANDLER
# ═══════════════════════════════════════════════════════════════════════════

async def _handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    uid = update.effective_user.id
    if DB_OK and not is_admin(uid):
        await update.message.reply_text("Only admins can upload mocks.")
        return
    if not doc:
        return
    fname = doc.file_name or "file.html"
    if not fname.lower().endswith((".html", ".htm")):
        await update.message.reply_text("Only .html / .htm supported.")
        return

    status = await update.message.reply_text("Downloading...")
    try:
        tf = tempfile.NamedTemporaryFile(suffix=Path(fname).suffix, delete=False)
        tpath = tf.name; tf.close()
        await (await context.bot.get_file(doc.file_id)).download_to_drive(tpath)
        with open(tpath, "r", encoding="utf-8") as f:
            html = f.read()
        os.unlink(tpath)

        # Detect editorial files by filename or content keywords
        is_editorial = ('editorial' in fname.lower() or
                       'editorial' in html[:2000].lower() or
                       'vocab' in fname.lower() or
                       'cloze' in html[:3000].lower())

        if is_editorial and not is_admin(uid):
            await status.edit_text("Only admins can upload editorials.")
            return

        if is_editorial:
            # Editorial flow: inject tracker, store as editorial
            editorial_id = register_editorial(uid, title=fname.replace('.html','')[:80],
                                              source_file=fname)
            # Inject tracker into HTML
            tracked_html = inject_editorial_tracker(html, editorial_id)
            # Save to mocks_storage for serving
            store_path = Path(__file__).parent / "mocks_storage" / f"{editorial_id}.html"
            store_path.write_text(tracked_html, encoding="utf-8")
            await status.edit_text(
                f"📰 *Editorial uploaded!*\n"
                f"ID: `{editorial_id}`\n"
                f"Tracker injected — users can submit results.\n\n"
                f"_Use /editorial to list all._",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        content, changes = universal_rebrand(html)
        questions, ttype = extract_questions(content)
        qn = len(questions) if questions else 0
        stats = {"rebranded": changes, "extracted": qn}

        _pending[uid] = {
            "html": content, "questions": questions, "ttype": ttype,
            "msg_id": status.message_id, "chat_id": update.effective_chat.id,
            "stats": stats, "original_html": html, "fname": fname,
        }

        kb = [[InlineKeyboardButton("Rebrand + Upload", callback_data="act:rebrand")]]
        if questions:
            kb.append([InlineKeyboardButton("Gemini Rephrase + Upload", callback_data="act:rephrase")])

        await status.edit_text(
            f"*{escape_markdown(fname, version=2)}*\n- {changes} brand replacements\n- {qn} questions\n\nChoose action:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        log.exception("File error")
        await status.edit_text(f"Error: {e}")


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if text in ("🎨 Rebrand Mock", "📤 Upload Mock", "📰 Upload Editorial") and not is_admin(uid):
        await update.message.reply_text("Admin only.")
        return

    if text == "🎨 Rebrand Mock":
        await update.message.reply_text("Send me an .html mock file to rebrand.")
    elif text == "📤 Upload Mock":
        await update.message.reply_text("Send the A2Z-rebranded .html mock. I'll register it with a unique ID.")
    elif text == "📰 Upload Editorial":
        await update.message.reply_text("Send the editorial .html file to add to the study browser.")


async def _callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    data = query.data or ""

    # ── Dashboard / Invite / Verify callbacks (no pending needed) ──
    if data == "cmd:dashboard":
        await query.message.delete()
        await _dashboard(update, context)
        return
    if data == "cmd:invite":
        await query.message.delete()
        await _invite_cmd(update, context)
        return
    if data == "cmd:verify":
        await query.message.delete()
        await _verify_cmd(update, context)
        return
    if data.startswith("lb:"):
        mock_id = data.replace("lb:", "")
        context.args = [mock_id]
        await query.message.delete()
        await _leaderboard(update, context)
        return

    # ── Mock processing callbacks ──
    pending = _pending.pop(uid, None)
    if not pending:
        await query.edit_message_text("Session expired. Send the file again.")
        return

    action = data.replace("act:", "")

    try:
        if action == "rebrand":
            await query.edit_message_text("⏳ Processing...")
            questions, ttype = pending["questions"], pending["ttype"]
            content, stats = pending["html"], pending["stats"]
            if questions:
                questions = _auto_fill_options(questions)
                questions = inject_cta(questions)
                title, section = _extract_mock_info(pending["html"], questions)
                # Register mock in DB
                mock_id = ""
                if DB_OK:
                    mock_id = register_mock(uid, title, topic=section, section=section,
                                           source_file=pending.get("fname", ""),
                                           question_count=len(questions),
                                           timer_minutes=max(5, int(len(questions) * 0.5)))
                    register_questions(mock_id, questions)
                    pending["mock_id"] = mock_id
                content = render_template(questions, mock_title=title, section=section, mock_id=mock_id)
                if content is None:
                    content = rebuild_html(pending["html"], questions, ttype)
                    content = inject_footer_banner(content)
            else:
                content = inject_footer_banner(pending["html"])
        else:
            # Rephrase path
            q_count = len(pending.get("questions") or [])
            state = ProcessState(total_questions=q_count)
            state.phase = "rebranding"
            await query.edit_message_text(state.render())
            progress_task = asyncio.create_task(_progress_loop(state, query.message))
            try:
                content, stats = await process_mock(pending["original_html"], rephrase=True, state=state)
            finally:
                state.phase = "done"
                await asyncio.sleep(0.5)
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            try:
                await query.message.delete()
            except Exception:
                pass
            tf = tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False)
            tf.write(content); tpath = tf.name; tf.close()
            cap = [
                "✅ Customised mock ready!",
                f"• {stats.get('rebranded', 0)} brand replacements",
            ]
            if stats.get("extracted", 0):
                cap.append(f"• {stats['extracted']} questions processed")
            if stats.get("rephrased", 0):
                cap.append(f"• {stats['rephrased']} questions rephrased by Gemini")
            cap.append(f"\n{CHANNEL_LINK}")
            with open(tpath, "rb") as f:
                await context.bot.send_document(
                    chat_id=pending["chat_id"],
                    document=f,
                    filename="A2Z_" + pending.get("fname", "mock.html"),
                    caption="\n".join(cap),
                )
            os.unlink(tpath)
            return

        await _deliver(query, content, pending, stats)

    except Exception as e:
        log.exception("Process error")
        await query.edit_message_text(f"Error: {e}")


async def _deliver(query, content: str, pending: Dict, stats: Dict):
    tf = tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False)
    tf.write(content); tpath = tf.name; tf.close()

    cap = [
        "✅ Customised mock ready!",
        f"• {stats.get('rebranded', 0)} brand replacements",
    ]
    if stats.get("extracted", 0):
        cap.append(f"• {stats['extracted']} questions processed")
    if stats.get("rephrased", 0):
        cap.append(f"• {stats['rephrased']} questions rephrased by Gemini")
    cap.append(f"\n{CHANNEL_LINK}")
    mock_id = pending.get("mock_id", "")
    filename = f"A2Z_{mock_id}.html" if mock_id else "A2Z_" + pending.get("fname", "mock.html")

    with open(tpath, "rb") as f:
        msg = await query.message.reply_document(
            document=f, filename=filename,
            caption="\n".join(cap),
        )
    os.unlink(tpath)

    # Save to storage folder for mini app access
    if mock_id:
        STORAGE_DIR = Path(__file__).parent / "mocks_storage"
        STORAGE_DIR.mkdir(exist_ok=True)
        store_path = STORAGE_DIR / f"{mock_id}.html"
        store_path.write_text(content, encoding="utf-8")
        # Store file_id in DB for re-sending
        if DB_OK:
            db_execute(
                "UPDATE mocks SET file_hash = ? WHERE mock_id = ?",
                (msg.document.file_id, mock_id),
            )
            db_commit()
        log.info("Mock %s saved to storage + file_id stored", mock_id)

    await query.delete_message()


# ═══════════════════════════════════════════════════════════════════════════
# MINI APP WEBAPP DATA HANDLER
# ═══════════════════════════════════════════════════════════════════════════

async def _webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle data sent from Telegram Mini App via WebApp.sendData()."""
    if not DB_OK:
        return
    uid = update.effective_user.id
    try:
        data = json.loads(update.message.web_app_data.data)
    except Exception:
        return
    action = data.get("action", "")

    if action == "get_mocks":
        # Return all available mocks grouped by topic
        mocks = db_fetchall("SELECT * FROM mocks ORDER BY created_at DESC LIMIT 50")
        mock_list = [{
            "mock_id": m["mock_id"], "title": m["title"], "topic": m["topic"],
            "question_count": m["question_count"], "timer_minutes": m["timer_minutes"],
            "total_attempts": m["total_attempts"], "created_at": m["created_at"][:10],
            "section": m["section"],
            "scheduled_at": m.get("scheduled_at",""), "active_at": m.get("active_at",""),
            "expires_at": m.get("expires_at",""), "benchmark": m.get("benchmark_score"),
        } for m in mocks]
        # Store in CloudStorage for mini app
        resp = json.dumps(mock_list)
        await update.message.reply_text(
            f"📋 *Mocks Available:* {len(mock_list)}\n\n_Data synced to mini app._",
            parse_mode=ParseMode.MARKDOWN,
        )
        # Also set CloudStorage if supported
        log.info("Mini app requested mock list — %d mocks", len(mock_list))

    elif action == "get_mock":
        mock_id = data.get("mock_id", "")
        mock = db_fetchone("SELECT * FROM mocks WHERE mock_id = ?", (mock_id,))
        if mock and mock["file_hash"]:
            # Re-send the stored file
            await update.message.reply_document(
                document=mock["file_hash"],
                filename=f"A2Z_{mock_id}.html",
                caption=f"📝 *{mock['title']}*\n{mock['question_count']} Qs · {mock['timer_minutes']} min\n\nOpen this file to take the test. Submit results via the mini app.",
                parse_mode=ParseMode.MARKDOWN,
            )
        elif mock:
            # Try from local storage
            store_path = Path(__file__).parent / "mocks_storage" / f"{mock_id}.html"
            if store_path.exists():
                with open(store_path, "rb") as f:
                    msg = await update.message.reply_document(
                        document=f,
                        filename=f"A2Z_{mock_id}.html",
                        caption=f"📝 *{mock['title']}*\n{mock['question_count']} Qs · {mock['timer_minutes']} min",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                # Save file_id for future
                db_execute("UPDATE mocks SET file_hash = ? WHERE mock_id = ?", (msg.document.file_id, mock_id))
                db_commit()
            else:
                await update.message.reply_text("Mock file not found. Ask admin to re-upload.")
        else:
            await update.message.reply_text("Mock not found in database.")

    elif action == "get_leaderboard":
        mock_id = data.get("mock_id", "")
        lb = get_leaderboard(mock_id, 15)
        mock = get_mock(mock_id)
        mock_title = mock["title"] if mock else mock_id
        # Build leaderboard JSON for mini app
        lb_data = []
        for r in (lb or []):
            lb_data.append({
                "rank": r["rank"], "name": (r.get("first_name") or r.get("name","?"))[:20],
                "score": r["score"], "total": r["correct"] + r["wrong"],
                "accuracy": round(r["accuracy"], 1), "user_id": r.get("user_id"),
            })
        # Update stored state with leaderboard
        stored = get_stored_state(uid)
        if stored:
            try:
                state_data = json.loads(stored)
                state_data["leaderboard"] = {"mock_id": mock_id, "title": mock_title, "entries": lb_data}
                store_state(uid, json.dumps(state_data))
            except Exception:
                pass
        # Send text reply to chat
        msg = f"🏆 *{mock_title}*\n\n"
        if not lb:
            msg += "_No attempts yet._"
        else:
            for r in lb[:10]:
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"], f"#{r['rank']}")
                msg += f"{medal} {r['name'][:15]} — {r['score']}/{r['correct']+r['wrong']} ({r['accuracy']}%)\n"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif action == "guild_create":
        name = data.get("name", "Untitled")
        ok, result = create_guild(db_execute, db_commit, uid, name)
        await update.message.reply_text(
            f"⚔️ Guild *{name}* created!\nShare this ID with friends: `{result}`" if ok else f"Failed: {result}",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif action == "guild_join":
        guild_id = data.get("guild_id", "")
        ok, result = join_guild(db_execute, db_commit, uid, guild_id)
        await update.message.reply_text(result)

    elif action == "get_guild":
        guild_info = None
        if GAME_OK:
            guild_info = get_guild_info(db_execute, uid)
        if guild_info:
            # Update stored state with guild data
            stored = get_stored_state(uid)
            if stored:
                try:
                    state_data = json.loads(stored)
                    state_data["guild"] = guild_info
                    store_state(uid, json.dumps(state_data))
                except Exception:
                    pass
            member_list = "\n".join(
                f"{'✅' if m.get('quest_done_today') else '⬜'} {m.get('first_name','?')} ({m.get('xp',0)} XP)"
                for m in guild_info.get("members", [])
            )
            await update.message.reply_text(
                f"⚔️ *{guild_info['name']}*\n"
                f"Multiplier: {guild_info.get('multiplier',1)}x\n\n"
                f"*Members:*\n{member_list}\n\n"
                f"Guild ID: `{guild_info['guild_id']}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("You are not in a guild. Create or join one.")

    elif action == "guild_leave":
        if GAME_OK:
            ok, result = leave_guild(db_execute, db_commit, uid)
            await update.message.reply_text(result)
            # Clear guild from stored state
            stored = get_stored_state(uid)
            if stored:
                try:
                    state_data = json.loads(stored)
                    state_data["guild"] = None
                    store_state(uid, json.dumps(state_data))
                except Exception:
                    pass
        else:
            await update.message.reply_text("⚠️ Game system unavailable.")

    elif action == "my_stats":
        user = db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (uid,))
        if user and GAME_OK:
            html_card = hunter_license_html(dict(user))
            import tempfile
            tf = tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False)
            tf.write(html_card); tpath = tf.name; tf.close()
            with open(tpath, "rb") as f:
                await update.message.reply_document(f, filename="Hunter_License.html")
            os.unlink(tpath)

    elif action == "get_auth_token":
        from a2z_db import get_user_auth_token
        token = get_user_auth_token(uid)
        await update.message.reply_text(
            f"🔑 *API Token*: `{token}`\n\n"
            f"_Use this to connect the mini app to the bot API._\n"
            f"_Keep it private._",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif action == "editorial_result":
        # User submitted editorial quiz results from tracker
        editorial_id = data.get("editorial_id", "")
        cloze_c = data.get("cloze_correct", 0)
        cloze_t = data.get("cloze_total", 0)
        jumble_c = data.get("jumble_correct", 0)
        jumble_t = data.get("jumble_total", 0)
        total_c = cloze_c + jumble_c
        total_t = cloze_t + jumble_t
        acc = round(total_c / total_t * 100, 1) if total_t > 0 else 0
        db_execute(
            "CREATE TABLE IF NOT EXISTS editorial_results (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, editorial_id TEXT, cloze_correct INTEGER, cloze_total INTEGER, jumble_correct INTEGER, jumble_total INTEGER, accuracy REAL, created_at TEXT DEFAULT (datetime('now')))"
        )
        db_commit()
        db_execute(
            "INSERT INTO editorial_results (user_id, editorial_id, cloze_correct, cloze_total, jumble_correct, jumble_total, accuracy) VALUES (?,?,?,?,?,?,?)",
            (uid, editorial_id, cloze_c, cloze_t, jumble_c, jumble_t, acc),
        )
        db_commit()
        if GAME_OK and acc >= 50:
            award_xp(db_execute, db_commit, uid, QUIZ_XP, f"Editorial quiz — {editorial_id}", f"editorial_{editorial_id}")
        log.info("Editorial result: user=%d id=%s score=%d/%d acc=%.1f%%", uid, editorial_id, total_c, total_t, acc)

    elif action == "get_editorials":
        editorials = list_editorials(20)
        if not editorials:
            await update.message.reply_text("No editorials available.")
            return
        lines = ["📰 *Editorial Study*", ""]
        for e in editorials:
            lines.append(f"• *{e['title'][:55]}* — {e.get('article_date','')[:10]}")
        lines.append("")
        lines.append("_Tap an editorial below to open it:_")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        # Send each editorial as a document
        for e in editorials[:5]:
            store_path = Path(__file__).parent / "mocks_storage" / f"{e['editorial_id']}.html"
            if store_path.exists():
                with open(store_path, "rb") as f:
                    await update.message.reply_document(
                        f, filename=f"{e['title'][:40]}.html",
                        caption=f"📰 {e['title'][:60]}",
                    )

    elif action == "get_editorial":
        ed_id = data.get("editorial_id", "")
        ed = db_fetchone("SELECT * FROM editorials WHERE editorial_id = ?", (ed_id,))
        if not ed:
            await update.message.reply_text("Editorial not found.")
            return
        # Try mocks_storage first, then original file
        store_path = Path(__file__).parent / "mocks_storage" / f"{ed_id}.html"
        orig_path = Path(__file__).parent / (ed.get("filename") or "")
        if store_path.exists():
            src = store_path
        elif orig_path and orig_path.exists():
            src = orig_path
        else:
            await update.message.reply_text("Editorial file not found.")
            return
        html = src.read_text(encoding="utf-8")
        # Inject tracker if not already injected
        if 'a2z-tracker' not in html:
            html = inject_editorial_tracker(html, ed_id)
            store_path.write_text(html, encoding="utf-8")
        import tempfile
        tf = tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False)
        tf.write(html); tpath = tf.name; tf.close()
        with open(tpath, "rb") as f:
            await update.message.reply_document(f, filename=f"Editorial_{ed['title'][:30]}.html",
                caption="📰 Open to study. Track answers & submit results!")
        os.unlink(tpath)

    elif action == "get_my_analytics":
        # Return full analytics: subject summary, topic breakdown, weak areas, trends
        subj_summary = get_user_subject_summary(uid) or []
        weak = get_user_weak_areas(uid) or []
        trend = get_user_score_trend(uid, 15) or []
        silly = get_user_silly_mistakes(uid) or []
        analytics = {
            "subject_summary": [dict(r) for r in subj_summary],
            "weak_areas": [dict(r) for r in weak],
            "score_trend": [dict(r) for r in trend],
            "silly_mistakes": [dict(r) for r in silly],
        }
        # Store for mini-app API
        stored = get_stored_state(uid)
        if stored:
            try:
                state_data = json.loads(stored)
                state_data["analytics"] = analytics
                store_state(uid, json.dumps(state_data))
            except Exception:
                pass
        summary = f"📊 *Analytics*\n"
        for s in subj_summary[:5]:
            bar = "🟢" if s["accuracy"] >= 70 else ("🟡" if s["accuracy"] >= 40 else "🔴")
            summary += f"{bar} {s['subject']}: {s['accuracy']}% ({s['attempts']} Qs)\n"
        if weak:
            summary += "\n⚠️ *Weak Areas:*\n"
            for w in weak[:3]:
                summary += f"• {w['topic']} ({w['chapter']}): {w['accuracy']}%\n"
        await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN)

    elif action == "get_mock_analysis":
        mock_id = data.get("mock_id", "")
        if not mock_id:
            await update.message.reply_text("Specify mock_id.")
            return
        mock = get_mock(mock_id)
        attempt = db_fetchone(
            "SELECT * FROM attempts WHERE user_id = ? AND mock_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (uid, mock_id),
        )
        if not attempt:
            await update.message.reply_text("No attempt found for this mock.")
            return
        responses = db_fetchall(
            """SELECT r.*, q.text, q.subject_id, q.topic_id, q.difficulty_level
               FROM responses r JOIN questions q ON r.question_id = q.question_id
               WHERE r.user_id = ? AND r.attempt_id = ?""",
            (uid, attempt["attempt_id"]),
        )
        mock_title = mock["title"] if mock else mock_id
        msg = (
            f"📊 *{mock_title}*\n\n"
            f"Score: {attempt['total_score']} | Accuracy: {attempt['accuracy']}%\n"
            f"Correct: {attempt['correct_count']} | Wrong: {attempt['wrong_count']} | Skipped: {attempt['skipped_count']}\n"
            f"Time: {int((attempt['total_time_sec'] or 0) // 60)}m {int((attempt['total_time_sec'] or 0) % 60)}s\n"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif action == "get_ai_insights":
        text = _generate_insights_text(uid)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        if GEMINI_KEYS:
            enhanced = await _generate_gemini_insights(uid)
            if enhanced:
                await update.message.reply_text(enhanced, parse_mode=ParseMode.MARKDOWN)

    elif action == "get_mock_ai_analysis":
        mock_id = data.get("mock_id", "")
        if not mock_id:
            await update.message.reply_text("Specify mock_id.")
            return
        analysis = _generate_ai_mock_analysis(uid, mock_id)
        await update.message.reply_text(analysis, parse_mode=ParseMode.MARKDOWN)

    elif action == "complete_quest":
        if GAME_OK:
            complete_daily_quest(db_execute, db_commit, uid)
            deal_raid_damage(db_execute, db_commit, uid, 1, "quest_complete")
            inviter = verify_referral_by_action(uid)
            if inviter:
                award_xp(db_execute, db_commit, inviter, INVITE_XP, "Referral verified — friend completed quest", f"invite_q_{uid}")
                try:
                    await context.bot.send_message(inviter,
                        f"🎯 *Referral Verified!*\n+{INVITE_XP} XP. Your friend just completed a daily quest.\nCheck /verify to see your invite status.",
                        parse_mode=ParseMode.MARKDOWN)
                except Exception: pass
            user = db_fetchone("SELECT xp, rank, streak_days FROM users WHERE telegram_id = ?", (uid,))
            if user:
                await update.message.reply_text(f"✅ Quest completed!\n{user['xp']} XP | Rank {user['rank']} | Streak: {user['streak_days']}")
        else:
            await update.message.reply_text("⚠️ Game system unavailable.")


async def _trio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create or join a study trio."""
    if not DB_OK:
        await update.message.reply_text("Database not available.")
        return
    uid = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text(
            "👥 *Study Trio*\n\nCreate: /trio create\nJoin: /trio join <code>\n\n_Invite 2 friends. All 3 complete the same mock → 15 days premium access!_",
            parse_mode=ParseMode.MARKDOWN)
        return
    sub = args[0].lower()
    if sub == "create":
        code = create_trio(uid)
        await update.message.reply_text(f"👥 *Trio Created!*\nShare this code: `{code}`\n\nFriends join with: /trio join {code}\n_All 3 must complete the same mock to unlock 15 days premium access._", parse_mode=ParseMode.MARKDOWN)
    elif sub == "join" and len(args) >= 2:
        ok = join_trio(args[1], uid)
        await update.message.reply_text("✅ Joined the trio!" if ok else "❌ Failed. Code invalid or trio full.")
    else:
        await update.message.reply_text("Usage: /trio create | /trio join <code>")

# CLI MODE
# ═══════════════════════════════════════════════════════════════════════════
async def _cli_process(path: str, rephrase: bool):
    p = Path(path)
    if p.is_dir():
        files = list(p.glob("*.html")) + list(p.glob("*.htm"))
        print(f"Processing {len(files)} files in {p} ...\n")
        for f in files:
            await _cli_one(str(f), rephrase)
    else:
        await _cli_one(str(p), rephrase)


async def _cli_one(filepath: str, rephrase: bool):
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()
    content, stats = await process_mock(html, rephrase=rephrase)
    out = str(Path(filepath).parent / ("A2Z_" + Path(filepath).name))
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [OK] {Path(filepath).name}")
    print(f"       Rebrand: {stats['rebranded']} | Extracted: {stats.get('extracted',0)} | Rephrased: {stats.get('rephrased',0)}")
    print(f"       -> {out}\n")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════
def main():
    if len(sys.argv) > 1:
        target = sys.argv[1]
        do_rephrase = "--rephrase" in sys.argv or "-r" in sys.argv
        asyncio.run(_cli_process(target, do_rephrase))
        return

    if not TELEGRAM_OK:
        print("Install: pip install python-telegram-bot"); sys.exit(1)

    log.info("KeyManager: %d keys loaded", len(GEMINI_KEYS))

    # Ensure storage directory exists
    (Path(__file__).parent / "mocks_storage").mkdir(exist_ok=True)

    app = Application.builder().token(BOT_TOKEN).build()

    # Core handlers (all users)
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _help))

    # Admin commands
    app.add_handler(CommandHandler("admin", _admin))
    app.add_handler(CommandHandler("dashboard", _dashboard))
    app.add_handler(CommandHandler("leaderboard", _leaderboard))
    app.add_handler(CommandHandler("invite", _invite_cmd))
    app.add_handler(CommandHandler("verify", _verify_cmd))
    app.add_handler(CommandHandler("mystats", _mystats))
    app.add_handler(CommandHandler("guild", _guild_cmd))
    app.add_handler(CommandHandler("access", _access_cmd))
    app.add_handler(CommandHandler("challenge", _challenge_cmd))
    app.add_handler(CommandHandler("raid", _raid_cmd))
    app.add_handler(CommandHandler("editorial", _editorial_cmd))
    app.add_handler(CommandHandler("trio", _trio_cmd))

    # File upload (admin-only enforced in handler)
    app.add_handler(MessageHandler(filters.Document.ALL, _handle_file))
    # Keyboard buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))
    # Mini App WebApp data
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, _webapp_data))
    # Callbacks
    app.add_handler(CallbackQueryHandler(_callback))

    log.info("🤖 A2Z Updates Bot is running ...")

    # Start API server for mini-app two-way communication (runs on same event loop)
    if API_OK:
        try:
            loop = asyncio.get_event_loop()
            api = APIServer(port=8765)
            loop.run_until_complete(api.start())
        except Exception as e:
            log.warning("API server failed to start: %s", e)

    # Background scheduler tasks
    async def _scheduler_loop():
        """Run periodic maintenance: daily quests, rank decay, premium expiry."""
        while True:
            now = datetime.now()
            # IST offset: +5:30
            ist_hour = (now.hour + 5 + (now.minute >= 30 and 1 or 0)) % 24
            try:
                if DB_OK and GAME_OK:
                    # Daily quest auto-send at 6 AM IST
                    if 6 <= ist_hour < 7 and getattr(_scheduler_loop, '_quest_sent_date', '') != now.strftime('%Y-%m-%d'):
                        users = db_fetchall("SELECT telegram_id FROM users WHERE telegram_id != 0")
                        for u in (users or []):
                            create_daily_quest(db_execute, db_commit, u["telegram_id"])
                        _scheduler_loop._quest_sent_date = now.strftime('%Y-%m-%d')
                        log.info("Scheduler: Daily quests created for %d users", len(users or []))

                    # Rank decay check at midnight IST
                    if ist_hour == 0 and getattr(_scheduler_loop, '_decay_done_date', '') != now.strftime('%Y-%m-%d'):
                        users = db_fetchall("SELECT telegram_id FROM users WHERE telegram_id != 0")
                        for u in (users or []):
                            apply_rank_decay(db_execute, db_commit, u["telegram_id"])
                        _scheduler_loop._decay_done_date = now.strftime('%Y-%m-%d')
                        log.info("Scheduler: Rank decay checked for %d users", len(users or []))

                    # Premium access expiry check (hourly)
                    if getattr(_scheduler_loop, '_expiry_last_run', 0) != now.hour:
                        db_execute(
                            "UPDATE users SET premium_access_expiry = NULL, premium_tier = 'free' "
                            "WHERE premium_access_expiry IS NOT NULL AND premium_access_expiry < date('now')"
                        )
                        db_commit()
                        _scheduler_loop._expiry_last_run = now.hour
            except Exception as e:
                log.warning("Scheduler error: %s", e)
            await asyncio.sleep(300)  # Run every 5 minutes

    try:
        asyncio.get_event_loop().create_task(_scheduler_loop())
    except Exception:
        pass

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
