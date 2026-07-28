@echo off
REM Push this folder to https://github.com/mikebretz/Sylvorin (run once with your GitHub login)
cd /d "%~dp0"
echo.
echo Pushing Sylvorin to GitHub...
echo Repo: https://github.com/mikebretz/Sylvorin
echo.
if not exist ".git" (
  git init
  git branch -M main
)
git remote remove origin 2>nul
git remote add origin https://github.com/mikebretz/Sylvorin.git
git add -A
git status
echo.
set /p CONFIRM="Commit and push all files? (Y/N): "
if /I not "%CONFIRM%"=="Y" exit /b 0
git commit -m "Sylvorin game files" 2>nul
git push -u origin main --force
echo.
if errorlevel 1 (
  echo Push failed. Log in to GitHub Desktop or run: gh auth login
) else (
  echo Done. Files are on https://github.com/mikebretz/Sylvorin
)
pause
