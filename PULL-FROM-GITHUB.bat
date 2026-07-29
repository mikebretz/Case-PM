@echo off
title Pull Sylvorin from GitHub to C:\Sylvorin
color 0B

set "SYLVORIN_REPO=https://github.com/mikebretz/Sylvorin.git"
set "FALLBACK_REPO=https://github.com/mikebretz/Case-PM.git"
set "FALLBACK_BRANCH=cursor/sylvorin-c-drive-c4a4"

echo ================================================
echo   Pull Sylvorin into C:\Sylvorin
echo ================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo Install Git first: SETUP-SYLVORIN.bat option 1
  pause
  exit /b 1
)

if not exist "C:\Sylvorin" mkdir "C:\Sylvorin"

REM --- Already a git repo: pull ---
if exist "C:\Sylvorin\.git" (
  cd /d C:\Sylvorin
  git fetch --all
  git pull
  if errorlevel 1 (
    echo Trying fallback branch from Case-PM...
    git remote set-url origin %FALLBACK_REPO%
    git fetch origin %FALLBACK_BRANCH%
    git checkout %FALLBACK_BRANCH%
    git pull origin %FALLBACK_BRANCH%
  )
  goto :success
)

REM --- First time clone: try Sylvorin repo ---
echo Trying %SYLVORIN_REPO% ...
git clone %SYLVORIN_REPO% C:\Sylvorin-temp 2>nul
if not errorlevel 1 (
  xcopy /E /I /Y "C:\Sylvorin-temp\*" "C:\Sylvorin\"
  rd /s /q "C:\Sylvorin-temp"
  cd /d C:\Sylvorin
  goto :success
)

echo Sylvorin repo empty or not ready — using GitHub branch...
git clone -b %FALLBACK_BRANCH% %FALLBACK_REPO% C:\Sylvorin-temp
if errorlevel 1 (
  echo Pull failed.
  pause
  exit /b 1
)
xcopy /E /I /Y "C:\Sylvorin-temp\*" "C:\Sylvorin\"
rd /s /q "C:\Sylvorin-temp"
cd /d C:\Sylvorin
echo.
echo To use github.com/mikebretz/Sylvorin later, run PUSH-TO-GITHUB.bat once.

:success
echo.
echo ================================================
echo   C:\Sylvorin updated from GitHub
echo ================================================
echo.
echo NEXT (Unreal 5.8 "not found" fix):
echo   1. Keep Unreal Engine OPEN
echo   2. Run FIND-MY-UNREAL.bat
echo   3. SETUP-SYLVORIN.bat option 2
echo.
pause
