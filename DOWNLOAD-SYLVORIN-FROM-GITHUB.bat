@echo off
title Download Sylvorin from GitHub
color 0B
setlocal EnableDelayedExpansion

echo ================================================
echo   Download Sylvorin to C:\Sylvorin
echo   Primary: github.com/mikebretz/Sylvorin
echo ================================================
echo.

if not exist "C:\Sylvorin" mkdir "C:\Sylvorin"

set "TARGET=C:\Sylvorin"
set "ZIP=%TEMP%\sylvorin-github.zip"
set "EXTRACT=%TEMP%\sylvorin-github-extract"
set "SYLVORIN_ZIP=https://github.com/mikebretz/Sylvorin/archive/refs/heads/main.zip"
set "FALLBACK_ZIP=https://github.com/mikebretz/Case-PM/archive/refs/heads/cursor/sylvorin-c-drive-c4a4.zip"

call :download_zip %SYLVORIN_ZIP% "Sylvorin main"
if errorlevel 1 goto :fallback

call :copy_extracted
if errorlevel 1 goto :fallback
goto :success

:fallback
echo.
echo Sylvorin repo empty or not ready — using Case-PM branch backup...
call :download_zip %FALLBACK_ZIP% "Case-PM sylvorin branch"
if errorlevel 1 goto :failed
call :copy_extracted
if errorlevel 1 goto :failed
echo.
echo TIP: Run PUBLISH-SYLVORIN-TO-GITHUB.bat once to fill github.com/mikebretz/Sylvorin
goto :success

:failed
echo.
echo DOWNLOAD FAILED.
echo Try in browser:
echo   %SYLVORIN_ZIP%
echo Or:
echo   %FALLBACK_ZIP%
pause
exit /b 1

:success
echo.
echo ================================================
echo   Files are now in C:\Sylvorin
echo ================================================
echo.
echo Next:
echo   1. OPEN-SYLVORIN-PROJECT.bat
echo   2. SETUP-GAME-NOW.txt
echo.
echo GitHub: https://github.com/mikebretz/Sylvorin
echo.
pause
exit /b 0

:download_zip
set "URL=%~1"
set "LABEL=%~2"
echo Downloading %LABEL% ...
echo %URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP%' -UseBasicParsing;" ^
  "if (Test-Path '%EXTRACT%') { Remove-Item '%EXTRACT%' -Recurse -Force };" ^
  "Expand-Archive -Path '%ZIP%' -DestinationPath '%EXTRACT%' -Force;" ^
  "$folder = Get-ChildItem '%EXTRACT%' -Directory | Select-Object -First 1;" ^
  "if (-not $folder) { throw 'Zip was empty' };" ^
  "$count = (Get-ChildItem $folder.FullName -Force | Measure-Object).Count;" ^
  "if ($count -lt 3) { throw 'Zip folder looks empty' }"
if errorlevel 1 exit /b 1
exit /b 0

:copy_extracted
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$folder = Get-ChildItem '%EXTRACT%' -Directory | Select-Object -First 1;" ^
  "Copy-Item -Path (Join-Path $folder.FullName '*') -Destination '%TARGET%' -Recurse -Force;" ^
  "Write-Host 'Copied from' $folder.Name 'to %TARGET%'"
if errorlevel 1 exit /b 1
exit /b 0
