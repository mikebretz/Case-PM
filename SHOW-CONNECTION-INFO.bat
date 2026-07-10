@echo off
title Case PM - Connection Info
cd /d "%~dp0"

echo ================================================
echo   Case PM - What Address Should Others Use?
echo ================================================
echo.

set "PORT=5000"
set "SERVER_RUNNING=0"

powershell -NoProfile -Command ^
  "if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 set "SERVER_RUNNING=1"

if "%SERVER_RUNNING%"=="0" (
    color 0E
    echo  STATUS: Case PM is NOT running on port %PORT%
    echo.
    echo  Start it with:  RUN-AS-SERVER.bat
    echo  ^(run.bat only works on THIS computer — not for remote login^)
    echo.
    goto :showip
)

echo  STATUS: Case PM server is RUNNING on port %PORT%
echo.

netsh advfirewall firewall show rule name="Case PM Server (TCP 5000)" >nul 2>&1
if errorlevel 1 (
    color 0E
    echo  WARNING: Windows Firewall may block other computers.
    echo  Run ALLOW-REMOTE-ACCESS.bat once ^(as administrator^).
    echo.
) else (
    echo  Firewall: OK — port %PORT% allowed
    echo.
)

:showip
echo  Addresses on THIS computer ^(for you only^):
echo    http://127.0.0.1:%PORT%
echo    http://localhost:%PORT%
echo.
echo  Give OTHER computers one of these ^(same Wi-Fi / office^):
echo.

set "FOUND=0"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command ^
  "$ip = (Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } ^| Select-Object -First 1 -ExpandProperty IPAddress); if (-not $ip) { $c = New-Object System.Net.Sockets.UdpClient; $c.Connect('8.8.8.8',80); $ip = $c.Client.LocalEndPoint.Address.ToString(); $c.Close() }; $ip"`) do (
    echo    http://%%I:%PORT%
    set "FOUND=1"
)

if "%FOUND%"=="0" (
    echo    ^(Could not detect IP — check Wi-Fi is connected^)
)

echo.
echo  Different network / over the internet?
echo    1. Keep RUN-AS-SERVER.bat running
echo    2. Run START-INTERNET-TUNNEL.bat
echo    3. Share the https://....trycloudflare.com link it prints
echo.
echo  Still "connection refused"?
echo    - Other PC must use http:// NOT https://
echo    - Both PCs on same Wi-Fi? Some guest networks block device-to-device
echo    - Try the internet tunnel instead
echo.
pause
