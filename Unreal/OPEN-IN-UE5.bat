@echo off
REM Open Sylvorin in Unreal Engine 5
set "PROJECT=C:\Sylvorin\Unreal\Sylvorin.uproject"

if not exist "%PROJECT%" (
  echo Project not found: %PROJECT%
  echo Put Sylvorin files in C:\Sylvorin first.
  pause
  exit /b 1
)

echo Opening Sylvorin in Unreal Engine...
echo Project: %PROJECT%
echo.
echo First time: allow Visual Studio rebuild when prompted.
echo Docs: C:\Sylvorin\Unreal\Docs\GETTING-STARTED.md
echo.

start "" "%PROJECT%"
pause
