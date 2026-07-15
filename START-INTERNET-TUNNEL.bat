@echo off
setlocal EnableExtensions
title Case PM - Internet Tunnel

:: Double-clicking a .bat closes the window when the script ends.
:: Re-launch inside a persistent cmd window so errors stay visible.
if /i not "%~1"=="--run" (
    cd /d "%~dp0" 2>nul
    cmd /k "%~f0" --run
    exit /b 0
)

cd /d "%~dp0"
if errorlevel 1 (
    echo ERROR: Could not open folder: %~dp0
    goto :done
)

set "TUNNEL_DIR=%~dp0tools"
set "CLOUDFLARED=%TUNNEL_DIR%\cloudflared.exe"
set "PORT=5000"
set "LOG_FILE=%TUNNEL_DIR%\tunnel.log"
set "DIAG_FILE=%TUNNEL_DIR%\tunnel-startup.log"

if not exist "%TUNNEL_DIR%" mkdir "%TUNNEL_DIR%" 2>nul

echo [%date% %time%] START-INTERNET-TUNNEL.bat > "%DIAG_FILE%"
echo Folder: %~dp0>> "%DIAG_FILE%"

echo ================================================
echo   Case PM - Share Over the Internet
echo ================================================
echo.
echo REQUIREMENTS:
echo   1. Case PM running in another window: RUN-AS-SERVER.bat
echo   2. Internet on this PC
echo.
echo Do NOT use run.bat for remote access.
echo.

if not exist "%CLOUDFLARED%" (
    echo Downloading Cloudflare Tunnel tool ^(one-time, ~20 MB^)...
    echo Please wait...
    echo.
    call :download_cloudflared
    if errorlevel 1 goto :done
    echo Download complete.
    echo.
)

if not exist "%CLOUDFLARED%" (
    echo ERROR: cloudflared.exe was not found after download.
    echo See: %DIAG_FILE%
    goto :done
)

echo Verifying cloudflared...
"%CLOUDFLARED%" version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo ERROR: cloudflared.exe cannot run on this PC.
    echo.
    echo Common causes:
    echo   - Antivirus blocked or deleted the file
    echo   - Add an exception for: %CLOUDFLARED%
    echo   - Re-run this script to download again
    echo.
    goto :done
)

echo Checking Case PM on port %PORT%...
set "SERVER_OK=0"
netstat -an | findstr /R /C:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 set "SERVER_OK=1"
if "%SERVER_OK%"=="0" (
    netstat -an | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
    if not errorlevel 1 set "SERVER_OK=1"
)

if "%SERVER_OK%"=="0" (
    color 0E
    echo.
    echo *** Case PM is NOT running on port %PORT% ***
    echo.
    echo Fix:
    echo   1. Open a FIRST window:  RUN-AS-SERVER.bat
    echo   2. Wait for "CASE PM SERVER" banner
    echo   3. Run this script again in a SECOND window
    echo.
    goto :done
)

echo Server is running on port %PORT%.
echo.
echo ================================================
echo   TUNNEL STARTING - keep this window open
echo ================================================
echo.
echo In 10-30 seconds look for a line like:
echo   https://something-random.trycloudflare.com
echo.
echo Share THAT link with remote users.
echo Log: %LOG_FILE%
echo.
echo If no link appears, try: START-INTERNET-TUNNEL-HTTP2.bat
echo ================================================
echo.

"%CLOUDFLARED%" tunnel --url http://127.0.0.1:%PORT% --logfile "%LOG_FILE%" --loglevel info
set "TUNNEL_EXIT=%ERRORLEVEL%"

echo.
if not "%TUNNEL_EXIT%"=="0" (
    color 0C
    echo Tunnel exited with error code %TUNNEL_EXIT%.
    echo Check log: %LOG_FILE%
    echo Try: START-INTERNET-TUNNEL-HTTP2.bat
) else (
    echo Tunnel stopped.
)

:done
echo.
echo Diagnostic log: %DIAG_FILE%
echo.
pause
endlocal
exit /b 0


:download_cloudflared
echo Downloading...>> "%DIAG_FILE%"
where curl >nul 2>&1
if not errorlevel 1 (
    curl -fsSL -o "%CLOUDFLARED%" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if not errorlevel 1 if exist "%CLOUDFLARED%" exit /b 0
    echo curl download failed>> "%DIAG_FILE%"
)

where powershell >nul 2>&1
if errorlevel 1 (
    echo ERROR: Need PowerShell or curl to download cloudflared.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue';" ^
  "try { Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CLOUDFLARED%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    color 0C
    echo Download failed. Check internet connection and try again.
    exit /b 1
)
exit /b 0
