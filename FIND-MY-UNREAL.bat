@echo off
title Find Unreal Engine (use while UE 5.8 is RUNNING)
color 0E

echo ================================================
echo   Find Unreal Engine on this PC
echo   TIP: Keep Unreal Engine 5.8 OPEN while running this
echo ================================================
echo.

if not exist "C:\Sylvorin\scripts\find-unreal.ps1" (
  echo Missing scripts. Run PULL-FROM-GITHUB.bat first.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Sylvorin\scripts\find-unreal.ps1" save

echo.
echo Saved to C:\Sylvorin\unreal.paths.cfg
echo.
type C:\Sylvorin\unreal.paths.cfg
echo.
echo Now run SETUP-SYLVORIN.bat option 4 to verify, then option 2.
pause
