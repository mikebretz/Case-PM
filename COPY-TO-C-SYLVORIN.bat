@echo off
REM Copy these Sylvorin files to C:\Sylvorin (run from the folder that has INSTALL-DESKTOP.bat)
echo Copying Sylvorin to C:\Sylvorin ...

if not exist "C:\Sylvorin" mkdir "C:\Sylvorin"

REM Do not copy node_modules, .git, dist if present
robocopy "%~dp0" "C:\Sylvorin" /E /XD node_modules .git dist venv logs /XF install.log

echo.
echo Files copied to C:\Sylvorin
echo Next: C:\Sylvorin\INSTALL-DESKTOP.bat
pause
