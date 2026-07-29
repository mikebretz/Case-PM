@echo off
title Fix Sylvorin - remove C++ build junk
cd /d "%~dp0"

echo Removing old C++ build files so Unreal opens without Visual Studio...
echo.

if exist "Unreal\Binaries" rd /s /q "Unreal\Binaries"
if exist "Unreal\Intermediate" rd /s /q "Unreal\Intermediate"
if exist "Unreal\.vs" rd /s /q "Unreal\.vs"
del /q "Unreal\*.sln" 2>nul
del /q "Unreal\Sylvorin.sln" 2>nul

echo.
echo  Done.
echo.
echo  NOW run: OPEN-SYLVORIN-PROJECT.bat
echo  (Opens UNREAL — not Visual Studio)
echo.
echo  If Visual Studio opens anyway, CLOSE IT.
echo  Only Unreal Engine is needed.
pause
