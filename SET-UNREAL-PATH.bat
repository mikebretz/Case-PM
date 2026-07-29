@echo off
title Set Unreal path manually
echo Paste the full path to UnrealEditor.exe
echo Example: C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe
echo.
echo In Epic Launcher: UE 5.8 -^> three dots -^> Installed Location
echo Then add \Engine\Binaries\Win64\UnrealEditor.exe
echo.
set /p UEPATH="Path: "
if not exist "%UEPATH%" (
  echo File not found: %UEPATH%
  pause
  exit /b 1
)
(
  echo # Sylvorin paths — manual
  echo UNREAL_EDITOR=%UEPATH%
) > C:\Sylvorin\unreal.paths.cfg
echo Saved. Run SETUP-SYLVORIN.bat option 2.
pause
