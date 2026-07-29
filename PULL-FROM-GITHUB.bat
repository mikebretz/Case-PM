@echo off
title Pull Sylvorin from GitHub to C:\Sylvorin
color 0B

set "SYLVORIN_REPO=https://github.com/mikebretz/Sylvorin.git"
set "FALLBACK_REPO=https://github.com/mikebretz/Case-PM.git"
set "FALLBACK_BRANCH=cursor/sylvorin-c-drive-c4a4"

echo ================================================
echo   Pull Sylvorin into C:\Sylvorin
echo   https://github.com/mikebretz/Sylvorin
echo ================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo Git not installed. Use DOWNLOAD-SYLVORIN-FROM-GITHUB.bat instead.
  pause
  exit /b 1
)

if not exist "C:\Sylvorin" mkdir "C:\Sylvorin"

if exist "C:\Sylvorin\.git" (
  cd /d C:\Sylvorin
  git remote set-url origin %SYLVORIN_REPO%
  git fetch origin
  git pull origin main
  if not errorlevel 1 goto :success
  echo Sylvorin repo empty — trying Case-PM backup branch...
  git fetch %FALLBACK_REPO% %FALLBACK_BRANCH%
  git checkout -B main FETCH_HEAD
  goto :success
)

echo Cloning %SYLVORIN_REPO% ...
git clone %SYLVORIN_REPO% C:\Sylvorin-temp
if not errorlevel 1 (
  xcopy /E /I /Y "C:\Sylvorin-temp\*" "C:\Sylvorin\"
  rd /s /q "C:\Sylvorin-temp"
  cd /d C:\Sylvorin
  if exist "Unreal\Sylvorin.uproject" goto :success
  rd /s /q "C:\Sylvorin-temp" 2>nul
)

echo First-time clone from backup branch...
git clone -b %FALLBACK_BRANCH% --single-branch %FALLBACK_REPO% C:\Sylvorin-temp
if errorlevel 1 (
  echo Pull failed. Try DOWNLOAD-SYLVORIN-FROM-GITHUB.bat
  pause
  exit /b 1
)
xcopy /E /I /Y "C:\Sylvorin-temp\*" "C:\Sylvorin\"
rd /s /q "C:\Sylvorin-temp"
cd /d C:\Sylvorin
echo.
echo Run PUBLISH-SYLVORIN-TO-GITHUB.bat once to use github.com/mikebretz/Sylvorin

:success
echo.
echo ================================================
echo   C:\Sylvorin updated from GitHub
echo ================================================
echo.
echo NEXT: OPEN-SYLVORIN-PROJECT.bat
echo.
pause
