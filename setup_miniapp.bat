@echo off
echo ====================================================
echo  A2Z Mini App - One-Click Deploy Setup
echo ====================================================
echo.
echo STEP 1: Create a GitHub repository
echo   Open: https://github.com/new
echo   Name: a2z-miniapp
echo   Keep it PUBLIC
echo   DO NOT add README, .gitignore, or license
echo   Click "Create repository"
echo.
echo STEP 2: Copy the repo URL (e.g., https://github.com/YOUR_USER/a2z-miniapp.git)
echo   Press ENTER when ready...
pause

set /p REPO_URL="Paste your GitHub repo URL: "
echo.

echo Adding remote and pushing...
git remote add origin %REPO_URL%
git branch -M main
git push -u origin main

echo.
echo STEP 3: Enable GitHub Pages
echo   1. Go to repo Settings ^> Pages
echo   2. Source: Deploy from a branch
echo   3. Branch: main / root
echo   4. Click Save
echo   5. Wait 30 seconds, your URL will be:
echo      https://YOUR_USER.github.io/a2z-miniapp/a2z_miniapp.html
echo.
echo STEP 4: Set up BotFather
echo   Open @BotFather on Telegram
echo   Send: /setmenubutton
echo   Select your bot
echo   Paste the GitHub Pages URL from Step 3
echo   Button text: Open Mini App
echo.
echo STEP 5: Set environment variable
echo   A2Z_WEBAPP_URL = your GitHub Pages URL
echo   Restart mainmock.py
echo.
echo ====================================================
echo  DONE! Mini App is live.
echo ====================================================
pause
