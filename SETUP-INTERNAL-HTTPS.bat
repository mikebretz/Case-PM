@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Case PM - Internal HTTPS Setup

echo ================================================================
echo   Case PM - Internal HTTPS (fix "Not Secure" in browser)
echo ================================================================
echo.
echo This creates a trusted HTTPS certificate for your office network
echo so other computers show a secure padlock instead of "Not Secure".
echo.
echo You will need mkcert (installed automatically if winget is available).
echo.

set "SSL_DIR=instance\ssl"
set "ENV_FILE=instance\server.env"
set "PORT=5000"

if not exist "instance" mkdir "instance" >nul 2>&1
if not exist "%SSL_DIR%" mkdir "%SSL_DIR%" >nul 2>&1

where mkcert >nul 2>&1
if errorlevel 1 (
    echo mkcert not found. Trying winget install...
    winget install -e --id FiloSottile.mkcert --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install mkcert automatically.
        echo Download from: https://github.com/FiloSottile/mkcert/releases
        echo Then run this file again.
        pause
        exit /b 1
    )
    echo.
    echo mkcert installed. You may need to close and reopen this window.
    echo.
)

where mkcert >nul 2>&1
if errorlevel 1 (
    echo ERROR: mkcert is still not in PATH. Open a new Command Prompt and run this again.
    pause
    exit /b 1
)

echo Installing local certificate authority on THIS computer...
mkcert -install
if errorlevel 1 (
    echo WARNING: mkcert -install had a problem. Continue anyway.
)

echo.
echo Detecting LAN IP address...
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command ^
  "$ip = (Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } ^| Select-Object -First 1 -ExpandProperty IPAddress); if (-not $ip) { $c = New-Object System.Net.Sockets.UdpClient; $c.Connect('8.8.8.8',80); $ip = $c.Client.LocalEndPoint.Address.ToString(); $c.Close() }; $ip"`) do set "LAN_IP=%%I"

if not defined LAN_IP (
    echo Could not detect LAN IP. Using localhost only.
    set "LAN_IP=127.0.0.1"
)

echo Using LAN IP: %LAN_IP%
echo.
echo Creating HTTPS certificate for localhost, 127.0.0.1, and %LAN_IP% ...
pushd "%SSL_DIR%"
mkcert -cert-file casepm-cert.pem -key-file casepm-key.pem localhost 127.0.0.1 %LAN_IP% casepm.local
if errorlevel 1 (
    popd
    echo ERROR: Certificate creation failed.
    pause
    exit /b 1
)
popd

echo.
echo Updating %ENV_FILE% ...
if not exist "%ENV_FILE%" copy /Y "server.env.example" "%ENV_FILE%" >nul

powershell -NoProfile -Command ^
  "$path = '%ENV_FILE%';" ^
  "$lines = if (Test-Path $path) { Get-Content $path } else { @() };" ^
  "$keys = @{ CASEPM_SSL_CERT = 'instance/ssl/casepm-cert.pem'; CASEPM_SSL_KEY = 'instance/ssl/casepm-key.pem'; CASEPM_HTTPS = '1'; CASEPM_REMOTE = '1'; CASEPM_HOST = '0.0.0.0' };" ^
  "foreach ($k in $keys.Keys) { $lines = $lines | Where-Object { $_ -notmatch ('^' + [regex]::Escape($k) + '=') }; $lines += ($k + '=' + $keys[$k]) };" ^
  "Set-Content -Path $path -Value $lines -Encoding ASCII"

echo.
echo ================================================================
echo   HTTPS setup complete on THIS server PC
echo ================================================================
echo.
echo   Use these addresses (note https://):
echo     https://127.0.0.1:%PORT%
echo     https://%LAN_IP%:%PORT%
echo.
echo   NEXT on OTHER computers in your office:
echo   ----------------------------------------
echo   Each PC must trust the mkcert root certificate once.
echo.
echo   Option A - Easy (each user, one time):
echo     1. Copy this file to their PC:
echo        %LOCALAPPDATA%\mkcert\rootCA.pem
echo     2. Double-click rootCA.pem -^> Install Certificate
echo     3. Store: Local Machine -^> Trusted Root Certification Authorities
echo.
echo   Option B - IT / Group Policy:
echo     Deploy rootCA.pem to all PCs via your domain GPO.
echo.
echo   Then restart Case PM with RUN-AS-SERVER.bat and share:
echo     https://%LAN_IP%:%PORT%
echo.
echo   In Program Settings - Security, you can also enable:
echo     - Force HTTPS
echo     - Require 2FA for Admins
echo.
pause
endlocal
