@echo off
title Case PM - Download Updates
color 0A
cd /d "%~dp0"

echo.
echo  ============================================================
echo    MIKE - DOWNLOAD UPDATES FOR CASE PM
echo  ============================================================
echo.
echo  You do NOT need to commit anything on GitHub.
echo  This script DOWNLOADS the fix to your computer.
echo.

git --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  GIT IS NOT INSTALLED on this PC.
    echo.
    echo  Do this instead:
    echo    1. Open: https://github.com/mikebretz/Case-PM
    echo    2. Click branch: cursor/mike-download-this-ab10
    echo    3. Click green Code - Download ZIP
    echo    4. Unzip and copy instance + uploads from old Case PM
    echo    5. Run run.bat
    echo.
    pause
    exit /b 1
)

echo  Downloading from GitHub branch: cursor/mike-download-this-ab10
echo.
git fetch origin
git checkout cursor/mike-download-this-ab10
if errorlevel 1 (
    echo  Branch not found locally, creating from GitHub...
    git fetch origin cursor/mike-download-this-ab10
    git checkout -b cursor/mike-download-this-ab10 origin/cursor/mike-download-this-ab10
)
git pull origin cursor/mike-download-this-ab10

echo.
echo  ============================================================
echo    DONE! Check below for version v57.0
echo  ============================================================
git log -1 --oneline
echo.
echo  NEXT:
echo    1. Close run.bat if open
echo    2. Double-click run.bat
echo    3. Press Ctrl+F5 in browser
echo    4. Console should say: Case PM v57.0
echo.
pause
