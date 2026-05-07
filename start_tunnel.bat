@echo off
echo ═══════════════════════════════════════════════════
echo   A2Z Bot API — Cloudflare Tunnel Setup
echo ═══════════════════════════════════════════════════
echo.
echo This exposes the bot API (port 8765) publicly so
echo the mini app can fetch data via fetch().
echo.
echo STEP 1: Install cloudflared (one time)
echo   winget install cloudflare.cloudflared
echo.
echo STEP 2: Start the tunnel
echo   cloudflared tunnel --url http://localhost:8765
echo.
echo STEP 3: Copy the *.trycloudflare.com URL from output
echo.
echo STEP 4: Paste it as API_BASE_URL in a2z_miniapp.html
echo   const API_BASE_URL = 'https://xxx.trycloudflare.com';
echo.
echo STEP 5: Refresh the mini app — API sync works!
echo.
echo ═══════════════════════════════════════════════════
echo Press any key to start the tunnel now...
pause >nul
cloudflared tunnel --url http://localhost:8765
