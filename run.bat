@echo off
cd /d "%~dp0"

echo ================================================
echo   Starting Case PM - Ultimate Version
echo ================================================
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not added to PATH.
    echo Please install Python 3.12 or 3.13 and try again.
    pause
    exit /b
)

:: Create virtual environment if it doesn't exist
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b
    )
    echo Virtual environment created successfully.
    echo.
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Check if requirements are installed (by checking for Flask)
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    echo This may take a minute on first run...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install requirements.
        pause
        exit /b
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
echo The application will open in your browser shortly...
echo.

:: Start the Flask app in a new window
start "" python app.py

:: Wait a few seconds for the server to fully start
timeout /t 5 /nobreak >nul

:: Open browser automatically
start http://127.0.0.1:5000

echo.
echo Case PM is now running.
echo Close this window to stop the application.
echo.
pause