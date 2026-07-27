@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if /i "%~1"=="firewall" goto :firewall_only
if /i not "%~1"=="elevated" (
    net session >nul 2>&1
    if errorlevel 1 (
        echo Requesting administrator permission for firewall configuration...
        powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
        exit /b 0
    )
)

echo ================================================================
echo   Case PM - Windows Server Setup (one time)
echo ================================================================
echo.
echo This prepares this PC as the Case PM server for your office:
echo   - Python virtual environment + packages
echo   - Windows Firewall rule for port 5000
echo   - Server config file (instance\server.env)
echo.
echo Your data in instance\ and uploads\ is not modified.
echo.

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
    color 0C
    echo ERROR: Python is not installed.
    echo Install Python 3.12+ from https://www.python.org/downloads/
    echo Check "Add python.exe to PATH" during install.
    goto :done_fail
)

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv venv
)
set "PY=venv\Scripts\python.exe"
if not exist "%PY%" (
    echo ERROR: venv\Scripts\python.exe not found.
    goto :done_fail
)

echo Installing / updating Python packages...
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo Package install failed. Try INSTALL-PACKAGES.bat
    goto :done_fail
)
echo Packages OK.

if not exist "instance" mkdir "instance" >nul 2>&1
if not exist "instance\server.env" (
    echo.
    echo Creating instance\server.env ...
    copy /Y "server.env.example" "instance\server.env" >nul
    call :load_env
    echo.
    set /p "LAN_SUBNET=Office LAN subnet for firewall (e.g. 192.168.1.0/24) or press Enter for private networks only: "
    if defined LAN_SUBNET (
        echo CASEPM_LAN_SUBNET=%LAN_SUBNET%>> "instance\server.env"
        set "CASEPM_LAN_SUBNET=%LAN_SUBNET%"
    )
) else (
    echo instance\server.env already exists — keeping your settings.
    call :load_env
)

call :configure_firewall

echo.
if not exist "instance\recovery.access" (
    echo RECOMMENDED: Set up owner break-glass recovery access.
    choice /C YN /M "Run SETUP-RECOVERY-ACCESS.bat now"
    if not errorlevel 2 call "%~dp0SETUP-RECOVERY-ACCESS.bat"
) else (
    echo Recovery access: configured.
)

echo.
echo ================================================================
echo   Windows Server setup complete
echo ================================================================
echo.
echo NEXT STEPS:
echo   1. Double-click RUN-AS-SERVER.bat  ^(keep window open^)
echo   2. Double-click SHOW-CONNECTION-INFO.bat for the LAN address to share
echo   3. Log in and CHANGE the default admin password
echo   4. Enable 2FA for Admin accounts in User Management
echo   5. Program Settings - Security: require_2fa_for_admins = true
echo.
echo Updates: PULL-AND-RESTART-SERVER.bat on this PC after GitHub pulls.
echo.
choice /C YN /M "Start the server now (RUN-AS-SERVER.bat)"
if not errorlevel 2 (
    endlocal
    call "%~dp0RUN-AS-SERVER.bat"
    exit /b 0
)
goto :done_ok

:firewall_only
cd /d "%~dp0"
call :load_env
call :configure_firewall
echo.
echo Firewall update complete.
pause
exit /b 0

:configure_firewall
set "RULE_NAME=Case PM Server (TCP 5000)"
set "PORT=5000"
if defined CASEPM_PORT set "PORT=%CASEPM_PORT%"

netsh advfirewall firewall delete rule name="%RULE_NAME%" >nul 2>&1

if defined CASEPM_LAN_SUBNET (
    echo Adding firewall rule: port %PORT% from %CASEPM_LAN_SUBNET% only...
    netsh advfirewall firewall add rule name="%RULE_NAME%" dir=in action=allow protocol=TCP localport=%PORT% remoteip=%CASEPM_LAN_SUBNET% profile=any
) else (
    echo Adding firewall rule: port %PORT% for private networks...
    netsh advfirewall firewall add rule name="%RULE_NAME%" dir=in action=allow protocol=TCP localport=%PORT% profile=private
)

if errorlevel 1 (
    echo WARNING: Could not add firewall rule.
) else (
    echo Firewall rule OK: %RULE_NAME%
)
exit /b 0

:load_env
call "%~dp0_load_server_env.bat"
exit /b 0

:done_fail
echo.
pause
exit /b 1

:done_ok
pause
exit /b 0
