@echo off
title Pull Sylvorin from GitHub
color 0B
set "REPO=https://github.com/mikebretz/Sylvorin.git"
set "BRANCH=main"

echo ================================================
echo   Pull Sylvorin from GitHub to C:\Sylvorin
echo   Repo: %REPO%
echo ================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo Git not installed. Run SETUP-SYLVORIN.bat option 1 first.
  pause
  exit /b 1
)

if not exist "C:\Sylvorin\.git" (
  echo First time — cloning to C:\Sylvorin ...
  if exist "C:\Sylvorin" (
    echo If clone fails, empty C:\Sylvorin and run this again.
  )
  git clone -b %BRANCH% %REPO% C:\Sylvorin-temp-clone
  if errorlevel 1 (
    echo.
    echo Clone failed. If Sylvorin repo is empty on GitHub, wait for push or use:
    echo   https://github.com/mikebretz/Case-PM/tree/cursor/sylvorin-c-drive-c4a4
    pause
    exit /b 1
  )
  xcopy /E /I /Y "C:\Sylvorin-temp-clone\*" "C:\Sylvorin\"
  rd /s /q "C:\Sylvorin-temp-clone"
  cd /d C:\Sylvorin
  goto :done
)

cd /d C:\Sylvorin
git remote set-url origin %REPO%
git fetch origin %BRANCH%
git checkout %BRANCH% 2>nul
git pull origin %BRANCH%

if errorlevel 1 (
  echo Pull had issues. Try: git stash && git pull origin %BRANCH%
  pause
  exit /b 1
)

:done
echo.
echo ================================================
echo   C:\Sylvorin is up to date from GitHub
echo ================================================
echo.
echo Next:
echo   FIND-MY-UNREAL.bat     (save UE 5.8 path while Unreal is running)
echo   SETUP-SYLVORIN.bat     option 2 = open project
echo.
pause
