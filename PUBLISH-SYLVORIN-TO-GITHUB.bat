@echo off
title Publish Sylvorin to GitHub (one time)
color 0E
setlocal EnableDelayedExpansion

echo ================================================================
echo   PUBLISH SYLVORIN TO GITHUB
echo   https://github.com/mikebretz/Sylvorin
echo ================================================================
echo.
echo This uploads the full game to YOUR Sylvorin repo so you can
echo download with PULL-FROM-GITHUB.bat or DOWNLOAD-SYLVORIN-FROM-GITHUB.bat
echo.
echo You may be asked to sign in to GitHub in a browser window.
echo.
pause

where git >nul 2>&1
if errorlevel 1 (
  echo Git is not installed. Install from https://git-scm.com/download/win
  pause
  exit /b 1
)

set "TARGET=C:\Sylvorin"
set "SYLVORIN_REPO=https://github.com/mikebretz/Sylvorin.git"
set "FALLBACK_ZIP=https://github.com/mikebretz/Case-PM/archive/refs/heads/cursor/sylvorin-c-drive-c4a4.zip"

if not exist "%TARGET%" mkdir "%TARGET%"

REM If project missing, download latest from Case-PM branch first
if not exist "%TARGET%\Unreal\Sylvorin.uproject" (
  echo Sylvorin.uproject not found — downloading latest files...
  call "%~dp0DOWNLOAD-SYLVORIN-FROM-GITHUB.bat"
  if not exist "%TARGET%\Unreal\Sylvorin.uproject" (
    echo Still missing Unreal project. Check internet and try again.
    pause
    exit /b 1
  )
)

cd /d "%TARGET%"

if not exist ".git" (
  echo Initializing git in %TARGET% ...
  git init
  git branch -M main
)

git remote remove origin 2>nul
git remote add origin %SYLVORIN_REPO%

echo.
echo Adding all files...
git add -A
git status --short

git diff --cached --quiet
if not errorlevel 1 (
  echo Nothing new to commit — trying push anyway...
) else (
  git commit -m "Sylvorin game + UE5 project"
)

echo.
echo Pushing to %SYLVORIN_REPO% ...
git push -u origin main --force

if errorlevel 1 (
  echo.
  echo ================================================================
  echo   PUSH FAILED — try GitHub Desktop instead:
  echo   1. File -^> Add local repository -^> C:\Sylvorin
  echo   2. Publish repository -^> mikebretz/Sylvorin
  echo ================================================================
  pause
  exit /b 1
)

echo.
echo ================================================================
echo   SUCCESS — Sylvorin is on GitHub
echo   https://github.com/mikebretz/Sylvorin
echo.
echo   Future updates on this PC: PULL-FROM-GITHUB.bat
echo   Fresh install elsewhere: DOWNLOAD-SYLVORIN-FROM-GITHUB.bat
echo ================================================================
pause
exit /b 0
