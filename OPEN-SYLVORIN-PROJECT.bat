@echo off
title Open Sylvorin
cd /d "%~dp0"

set "PROJECT=%~dp0Unreal\Sylvorin.uproject"

if not exist "%PROJECT%" (
  echo.
  echo  FILE NOT FOUND:
  echo  %PROJECT%
  echo.
  echo  Download the ZIP and copy files into this folder first:
  echo  https://github.com/mikebretz/Case-PM/archive/refs/heads/cursor/sylvorin-c-drive-c4a4.zip
  echo.
  pause
  exit /b 1
)

echo.
echo  Opening Sylvorin in Unreal Engine...
echo  %PROJECT%
echo.
echo  If Unreal asks to rebuild, click YES and wait.
echo.

start "" "%PROJECT%"

echo  Done. Unreal should open in 1-2 minutes.
pause
