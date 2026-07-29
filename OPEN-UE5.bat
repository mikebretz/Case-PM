@echo off
REM Opens Sylvorin in Unreal Engine 5 — use SETUP-SYLVORIN.bat if this fails
cd /d "C:\Sylvorin"
call "C:\Sylvorin\SETUP-SYLVORIN.bat" 
REM User picks option 2 from menu — or we auto-run open:
REM Fallback: direct launch
set "UE="
for %%V in (5.5 5.4 5.3) do (
  if exist "C:\Program Files\Epic Games\UE_%%V\Engine\Binaries\Win64\UnrealEditor.exe" (
    set "UE=C:\Program Files\Epic Games\UE_%%V\Engine\Binaries\Win64\UnrealEditor.exe"
    goto launch
  )
)
echo Unreal Engine 5 not installed. Run C:\Sylvorin\SETUP-SYLVORIN.bat and choose 1.
pause
exit /b 1
:launch
start "" "%UE%" "C:\Sylvorin\Unreal\Sylvorin.uproject"
echo Unreal Editor starting...
timeout /t 5
exit /b 0
