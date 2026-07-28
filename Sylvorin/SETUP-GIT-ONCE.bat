@echo off
REM One-time Git setup — push Sylvorin to github.com/mikebretz/Sylvorin
cd /d "%~dp0"
echo.
echo Sylvorin — Git setup
echo ====================
echo Repo: https://github.com/mikebretz/Sylvorin
echo.
git remote remove origin 2>nul
git remote add origin https://github.com/mikebretz/Sylvorin.git
git branch -M main
git push -u origin main
echo.
echo Done.
