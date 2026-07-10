@echo off
cd /d "%~dp0"

echo ============================================================
echo   Case PM - GET LATEST UPDATES (Drawing Export Fix)
echo ============================================================
echo.
echo This downloads the latest code from GitHub to your PC.
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git is not installed.
    echo Download from: https://git-scm.com/download/win
    pause
    exit /b 1
)

echo Step 1: Fetching from GitHub...
git fetch origin
if errorlevel 1 (
    echo ERROR: Could not reach GitHub. Check internet connection.
    pause
    exit /b 1
)

echo.
echo Step 2: Pulling latest main branch...
git checkout main 2>nul
git pull origin main
if errorlevel 1 (
    echo.
    echo Pull from main failed. Trying fix branch...
    git fetch origin cursor/drawing-export-fix-v2-ab10
    git checkout cursor/drawing-export-fix-v2-ab10
    if errorlevel 1 (
        echo ERROR: Could not get updates. See instructions in PULL-THIS-BRANCH.txt
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo   SUCCESS - Updates downloaded!
echo ============================================================
echo.
git log -1 --oneline
echo.
echo NOW DO THIS:
echo   1. Close Case PM completely (close run.bat window)
echo   2. Double-click run.bat to restart
echo   3. Press Ctrl+F5 in your browser
echo.
echo Then test: Drawings - Manage Drawing Sets - Docs button
echo.
pause
