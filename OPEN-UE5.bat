@echo off
title Open Sylvorin in Unreal Engine 5
cd /d "C:\Sylvorin"

if not exist "C:\Sylvorin\Unreal\Sylvorin.uproject" (
  echo Missing: C:\Sylvorin\Unreal\Sylvorin.uproject
  echo Run SETUP-SYLVORIN.bat first.
  pause
  exit /b 1
)

call "C:\Sylvorin\scripts\detect-tools.cmd"

if not defined UE_EDITOR (
  echo.
  echo  UNREAL ENGINE NOT FOUND BY SCRIPT
  echo  =================================
  echo  If Unreal IS installed (e.g. 5.8), pull latest files from GitHub
  echo  so C:\Sylvorin\scripts\find-unreal.ps1 is updated.
  echo.
  echo  Or open manually in Unreal:
  echo    File -^> Open Project -^> C:\Sylvorin\Unreal\Sylvorin.uproject
  echo.
  pause
  exit /b 1
)

echo Opening Unreal Editor with Sylvorin project...
echo %UE_EDITOR%
start "" "%UE_EDITOR%" "C:\Sylvorin\Unreal\Sylvorin.uproject"
echo.
echo If the editor does not appear, wait 1-2 minutes (first compile is slow).
echo.
pause
