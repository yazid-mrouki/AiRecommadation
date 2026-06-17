@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===============================================
echo   Moteur de recommandation IoT - LOCAL
echo ===============================================
echo.
REM Active le venv s'il existe (sinon utilise le Python systeme)
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
python main.py %*
echo.
pause
