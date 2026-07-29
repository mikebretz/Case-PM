@echo off
setlocal EnableDelayedExpansion
set "UE_EDITOR="
set "EPIC_LAUNCHER="
set "PS1=C:\Sylvorin\scripts\find-unreal.ps1"

if not exist "%PS1%" exit /b 0

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" 2^>nul`) do set "UE_EDITOR=%%I"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" epic 2^>nul`) do set "EPIC_LAUNCHER=%%I"

exit /b 0
