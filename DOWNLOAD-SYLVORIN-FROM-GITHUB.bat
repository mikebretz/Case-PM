@echo off
title Download Sylvorin from GitHub
color 0B

echo ================================================
echo   Download Sylvorin files to C:\Sylvorin
echo   (No Pull Request needed — direct download)
echo ================================================
echo.

if not exist "C:\Sylvorin" mkdir "C:\Sylvorin"

set "ZIP=%TEMP%\sylvorin-github.zip"
set "EXTRACT=%TEMP%\sylvorin-github-extract"
set "URL=https://github.com/mikebretz/Case-PM/archive/refs/heads/cursor/sylvorin-c-drive-c4a4.zip"

echo Downloading from GitHub...
echo %URL%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP%' -UseBasicParsing;" ^
  "if (Test-Path '%EXTRACT%') { Remove-Item '%EXTRACT%' -Recurse -Force };" ^
  "Expand-Archive -Path '%ZIP%' -DestinationPath '%EXTRACT%' -Force;" ^
  "$folder = Get-ChildItem '%EXTRACT%' -Directory | Select-Object -First 1;" ^
  "if (-not $folder) { throw 'Zip was empty' };" ^
  "Write-Host 'Copying from' $folder.FullName 'to C:\Sylvorin ...';" ^
  "Copy-Item -Path (Join-Path $folder.FullName '*') -Destination 'C:\Sylvorin' -Recurse -Force;" ^
  "Write-Host 'Done.'"

if errorlevel 1 (
  echo.
  echo DOWNLOAD FAILED.
  echo Open this link in your browser and extract to C:\Sylvorin:
  echo %URL%
  pause
  exit /b 1
)

echo.
echo ================================================
echo   Files are now in C:\Sylvorin
echo ================================================
echo.
echo Next steps:
echo   1. C:\Sylvorin\SETUP-SYLVORIN.bat  (option 4 = check install)
echo   2. C:\Sylvorin\SETUP-SYLVORIN.bat  (option 2 = open Unreal)
echo.
echo GitHub branch (not a PR):
echo   https://github.com/mikebretz/Case-PM/tree/cursor/sylvorin-c-drive-c4a4
echo.
pause
