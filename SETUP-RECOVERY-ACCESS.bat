@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"

echo ================================================
echo   Case PM - Setup Recovery Access (Owner Only)
echo ================================================
echo.
echo This creates instance\recovery.access on THIS computer only.
echo That file is your private backdoor credentials — back it up off-site.
echo It is never uploaded to git.
echo.

set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo ERROR: Python not found. Run run.bat once first to create the venv.
    pause
    exit /b 1
)

:input_email
set "RECOVERY_EMAIL="
set /p "RECOVERY_EMAIL=Recovery email: "
if not defined RECOVERY_EMAIL (
    echo Please enter an email address.
    goto input_email
)
echo %RECOVERY_EMAIL% | findstr /i /r ".*@.*\..*" >nul
if errorlevel 1 (
    echo That does not look like a valid email. Try again.
    goto input_email
)

:input_password
set "RECOVERY_PASSWORD="
echo.
echo Recovery password ^(you will see characters as you type — that is normal^):
set /p "RECOVERY_PASSWORD=Password: "
if not defined RECOVERY_PASSWORD (
    echo Password cannot be empty.
    goto input_password
)

set "RECOVERY_PASSWORD_CONFIRM="
set /p "RECOVERY_PASSWORD_CONFIRM=Confirm password: "
if not defined RECOVERY_PASSWORD_CONFIRM (
    echo Please confirm your password.
    goto input_password
)
if not "%RECOVERY_PASSWORD%"=="%RECOVERY_PASSWORD_CONFIRM%" (
    echo.
    echo Passwords do not match. Try again.
    echo.
    goto input_password
)

set "CASEPM_SETUP_EMAIL=%RECOVERY_EMAIL%"
set "CASEPM_SETUP_PASSWORD=%RECOVERY_PASSWORD%"
"%PY%" -u scripts\setup_recovery_access.py --from-batch
set "EXITCODE=%ERRORLEVEL%"
set "CASEPM_SETUP_EMAIL="
set "CASEPM_SETUP_PASSWORD="
set "RECOVERY_PASSWORD="
set "RECOVERY_PASSWORD_CONFIRM="

if not "%EXITCODE%"=="0" (
    echo.
    echo Setup failed.
    pause
    exit /b 1
)

echo.
echo Done. Use RECOVERY-ACCESS.bat anytime you need break-glass entry.
echo.
pause
exit /b 0
