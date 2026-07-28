@echo off
REM Pull latest Sylvorin files into C:\Sylvorin from GitHub
set "BRANCH=cursor/sylvorin-c-drive-c4a4"
set "REPO=https://github.com/mikebretz/Case-PM.git"

echo ================================================
echo   Pull Sylvorin to C:\Sylvorin
echo ================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo Install Git: https://git-scm.com/download/win
  pause
  exit /b 1
)

if not exist "C:\Sylvorin\.git" (
  echo Cloning to C:\Sylvorin ...
  if exist "C:\Sylvorin" (
    echo Folder C:\Sylvorin exists but is not a git repo.
    echo Move or delete it, then run this again.
    pause
    exit /b 1
  )
  git clone -b %BRANCH% %REPO% C:\Sylvorin
  if errorlevel 1 (
    echo Clone failed.
    pause
    exit /b 1
  )
  echo.
  echo Cloned. Next: C:\Sylvorin\INSTALL-DESKTOP.bat
  pause
  exit /b 0
)

cd /d C:\Sylvorin
git fetch origin %BRANCH%
git checkout %BRANCH%
git pull origin %BRANCH%

echo.
echo Updated C:\Sylvorin
echo Run C:\Sylvorin\INSTALL-DESKTOP.bat if this is your first time.
pause
