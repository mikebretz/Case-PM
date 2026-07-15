@echo off
setlocal EnableExtensions
title Case PM - Internet Tunnel

:: When double-clicked, Windows runs "cmd /c this.bat" and closes when done.
:: Open a NEW window that stays open (cmd /k).
if /i not "%~1"=="KEEPOPEN" (
    start "Case PM Internet Tunnel" cmd.exe /k call "%~f0" KEEPOPEN
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

echo [%date% %time%] START-INTERNET-TUNNEL.bat KEEPOPEN>> "%DIAG_FILE%"
echo Folder: %~dp0>> "%DIAG_FILE%"

echo.
echo ================================================
echo   Case PM - Internet Tunnel
echo ================================================
echo.
echo STEP 1: Case PM must be running in another window.
echo         Use RUN-AS-SERVER.bat  ^(NOT run.bat^)
echo.
echo STEP 2: This window must stay open while others connect.
echo.
echo Do NOT close this window until remote users are done.
echo.

if not exist "%CLOUDFLARED%" (
    echo Downloading tunnel tool ^(one-time, ~20 MB^)...
    echo Please wait 1-2 minutes...
    echo.
    call :download_cloudflared
    if errorlevel 1 goto :done
    echo Download complete.
    echo.
)

if not exist "%CLOUDFLARED%" (
    echo ERROR: cloudflared.exe missing after download.
    echo See: %DIAG_FILE%
    goto :done
)

echo Verifying cloudflared...
"%CLOUDFLARED%" version
if errorlevel 1 (
    color 0C
    echo.
    echo ERROR: cloudflared.exe blocked or will not run.
    echo Allow this file in antivirus: %CLOUDFLARED%
    goto :done
)

echo.
echo Checking port %PORT%...
set "SERVER_OK=0"
netstat -an | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 set "SERVER_OK=1"

if "%SERVER_OK%"=="0" (
    color 0E
    echo.
    echo *** Case PM is NOT running on port %PORT% ***
    echo.
    echo 1. Open another window
    echo 2. Double-click RUN-AS-SERVER.bat
    echo 3. Wait for "CASE PM SERVER" text
    echo 4. Run this tunnel again
    echo.
    goto :done
)

echo OK - Case PM is running.
echo.
echo ================================================
echo   STARTING TUNNEL - WAIT FOR YOUR LINK
echo ================================================
echo.
echo Look below for a line like:
echo   https://random-words.trycloudflare.com
echo.
echo Send THAT https link to remote users.
echo.

"%CLOUDFLARED%" tunnel --url http://127.0.0.1:%PORT% --logfile "%LOG_FILE%" --loglevel info
set "TUNNEL_EXIT=%ERRORLEVEL%"

echo.
if not "%TUNNEL_EXIT%"=="0" (
    color 0C
    echo Tunnel stopped with error %TUNNEL_EXIT%.
    echo Log: %LOG_FILE%
    echo Try: START-INTERNET-TUNNEL-HTTP2.bat
) else (
    echo Tunnel stopped.
)

:done
echo.
echo ================================================
echo Press any key to close this window...
echo ================================================
pause >nul
endlocal
exit /b 0


:download_cloudflared
echo download>> "%DIAG_FILE%"
where curl >nul 2>&1
if not errorlevel 1 (
    curl -fsSL -o "%CLOUDFLARED%" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if not errorlevel 1 if exist "%CLOUDFLARED%" exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CLOUDFLARED%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo Download failed - check internet connection.
    exit /b 1
)
exit /b 0
