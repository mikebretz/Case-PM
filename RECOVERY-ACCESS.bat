@echo off
:: Owner break-glass entry — forwards to EMERGENCY-RECOVERY.bat (same behavior).
cd /d "%~dp0"
call "%~dp0EMERGENCY-RECOVERY.bat" %*
