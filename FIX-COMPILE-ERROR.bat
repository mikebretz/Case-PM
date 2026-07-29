@echo off
title Fix Sylvorin compile error
cd /d "%~dp0"

echo.
echo  This deletes old failed C++ build files.
echo  Sylvorin is now Blueprint-only (no compile on open).
echo.

if exist "Unreal\Binaries" (
  echo Removing Unreal\Binaries ...
  rd /s /q "Unreal\Binaries"
)
if exist "Unreal\Intermediate" (
  echo Removing Unreal\Intermediate ...
  rd /s /q "Unreal\Intermediate"
)

echo.
echo  Done. Now double-click OPEN-SYLVORIN-PROJECT.bat
echo  When Unreal opens, click YES if it asks to rebuild
echo  (should open without C++ errors now).
echo.
pause
