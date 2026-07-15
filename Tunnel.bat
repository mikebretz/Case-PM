@echo off
:: Opens internet tunnel in a window that stays open.
cd /d "%~dp0"
start "Case PM Internet Tunnel" cmd.exe /k call "%~dp0START-INTERNET-TUNNEL.bat" KEEPOPEN
