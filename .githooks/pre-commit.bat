@echo off
REM Pre-commit hook: Blocks commits with leaked API keys
REM Place this in .git/hooks/pre-commit (no extension)

for /f %%i in ('git diff --cached --name-only') do (
    for /f "usebackq tokens=*" %%k in (`git show :%%i 2^>nul ^| findstr /c:"AIzaSy"`) do (
        echo [BLOCKED] API key found in %%i
        echo Remove the key and try again.
        exit /b 1
    )
    for /f "usebackq tokens=*" %%k in (`git show :%%i 2^>nul ^| findstr /c:"sk-"`) do (
        echo [BLOCKED] API key found in %%i
        exit /b 1
    )
)
exit /b 0
