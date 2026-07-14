@echo off
title Case PM - Remote Login Setup
cd /d "%~dp0"

echo ================================================
echo   Case PM - Let Other Computers Log In
echo ================================================
echo.
echo This sets up your PC as a Case PM server so coworkers,
echo tablets, or other computers can log in through a browser.
echo.
echo STEP 1 of 2: Windows Firewall (one time)
echo ----------------------------------------

netsh advfirewall firewall show rule name="Case PM Server (TCP 5000)" >nul 2>&1
if errorlevel 1 (
    echo Firewall rule not found — adding it now...
    echo ^(Click Yes if Windows asks for administrator permission^)
    echo.
    call "%~dp0ALLOW-REMOTE-ACCESS.bat"
) else (
    echo Firewall rule OK — port 5000 is allowed.
)

echo.
echo STEP 2 of 2: Start server for remote users
echo ----------------------------------------
echo.
echo IMPORTANT:
echo   - Do NOT use run.bat for remote access
echo   - Keep the server window OPEN while others are using Case PM
echo   - Share the http://192.168.x.x:5000 address shown below
echo     ^(NOT 127.0.0.1 — that only works on THIS computer^)
echo   - After GitHub updates: PULL-AND-RESTART-SERVER.bat on this PC
echo.
echo For someone on a DIFFERENT network ^(home, job site, etc.^):
echo   After the server starts, run START-INTERNET-TUNNEL.bat
echo   in a second window and share the https://....trycloudflare.com link.
echo.
pause

call "%~dp0RUN-AS-SERVER.bat"
