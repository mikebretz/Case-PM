@echo off
REM Push C:\Sylvorin to https://github.com/mikebretz/Sylvorin
cd /d "C:\Sylvorin"
if not exist "C:\Sylvorin\package.json" (
  echo Put Sylvorin files in C:\Sylvorin first.
  echo Use COPY-TO-C-SYLVORIN.bat or git clone.
  pause
  exit /b 1
)

if not exist ".git" (
  git init
  git branch -M main
)
git remote remove origin 2>nul
git remote add origin https://github.com/mikebretz/Sylvorin.git
git add -A
git commit -m "Sylvorin game files" 2>nul
git push -u origin main --force
if errorlevel 1 (
  echo Push failed — use GitHub Desktop or: gh auth login
) else (
  echo Done: https://github.com/mikebretz/Sylvorin
)
pause
