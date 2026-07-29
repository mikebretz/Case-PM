@echo off
REM Creates desktop shortcut "Sylvorin Setup" -> SETUP-SYLVORIN.bat
set "TARGET=C:\Sylvorin\SETUP-SYLVORIN.bat"
set "SHORTCUT=%USERPROFILE%\Desktop\Sylvorin Setup.lnk"

powershell -NoProfile -Command ^
  "$s = New-Object -ComObject WScript.Shell; $l = $s.CreateShortcut('%SHORTCUT%'); $l.TargetPath = '%TARGET%'; $l.WorkingDirectory = 'C:\Sylvorin'; $l.Description = 'Sylvorin - install and open UE5'; $l.Save()"

echo Desktop shortcut created: Sylvorin Setup
echo Double-click it anytime to open the setup menu.
pause

