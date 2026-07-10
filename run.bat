@echo off
cd /d "%~dp0"

echo ================================================
echo   Starting Case PM
echo ================================================
echo.

:: Find Python
set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"

if not defined PY (
    echo ERROR: Python is not installed or not in PATH.
    echo.
    echo Install Python 3.12+ from https://www.python.org/downloads/
    echo IMPORTANT: Check "Add python.exe to PATH" during install.
    echo.
    pause
    exit /b 1
)

%PY% --version
if errorlevel 1 (
    echo ERROR: Python found but does not run.
    pause
    exit /b 1
)

:: Create virtual environment if missing
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
    echo.
)

:: Always use venv Python (works even if activate.bat has issues)
set "PY=venv\Scripts\python.exe"
if not exist "%PY%" (
    echo ERROR: venv\Scripts\python.exe not found.
    pause
    exit /b 1
)

:: Upgrade pip inside venv (use python -m pip — never bare "pip")
echo Checking pip...
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo Installing pip into virtual environment...
    "%PY%" -m ensurepip --upgrade
)
"%PY%" -m pip install --upgrade pip --quiet

:: Install requirements if Flask not present
"%PY%" -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages — first run may take a few minutes...
    echo.
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install requirements.
        echo Try running INSTALL-PACKAGES.bat manually.
        pause
        exit /b 1
    )
    echo.
    echo Packages installed successfully.
    echo.
)

echo Starting Case PM server...
echo.
echo Login: admin@casepm.local
echo Password: admin123
echo.
echo For REMOTE access (others on your network or internet),
echo use RUN-AS-SERVER.bat instead of this file.
echo.
echo The application will open in your browser shortly...
echo.

set "CASEPM_HOST=127.0.0.1"
set "CASEPM_PORT=5000"
set "CASEPM_REMOTE=0"
set "CASEPM_DEBUG=1"

start "" "%PY%" app.py

timeout /t 5 /nobreak >nul
start http://127.0.0.1:5000

echo.
echo Case PM is now running.
echo Close this window to stop the application.
echo.
pause
