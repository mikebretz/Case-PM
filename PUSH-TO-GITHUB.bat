@echo off
REM One-time: push C:\Sylvorin to https://github.com/mikebretz/Sylvorin
cd /d C:\Sylvorin
echo Pushing to https://github.com/mikebretz/Sylvorin
echo Use your GitHub login if prompted.
echo.
if not exist ".git" (
  git init
  git branch -M main
)
git remote remove origin 2>nul
git remote add origin https://github.com/mikebretz/Sylvorin.git
git add -A
git commit -m "Sylvorin game + UE5 project" 2>nul
git push -u origin main --force
if errorlevel 1 (
  echo Use GitHub Desktop: Add existing repo C:\Sylvorin -^> publish to Sylvorin
) else (
  echo Done. Future updates: PULL-FROM-GITHUB.bat
)
pause
