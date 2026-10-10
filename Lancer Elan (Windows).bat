@echo off
REM Double-clique sur ce fichier pour lancer Elan sous Windows.
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" (where python >nul 2>nul && set PY=python)
if "%PY%"=="" goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" || goto nopython

if not exist ".venv\Scripts\python.exe" (
  echo Premiere installation, une minute...
  %PY% -m venv .venv || goto fail
)
fc /b requirements.txt .venv\req.txt >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto fail
  copy /y requirements.txt .venv\req.txt >nul
)

start "" cmd /c "timeout /t 3 >nul & start http://localhost:8742"
".venv\Scripts\python.exe" server.py
pause
exit /b 0

:nopython
echo.
echo Il faut Python 3.10 ou plus recent.
echo Installe-le depuis https://www.python.org/downloads/ en cochant "Add python.exe to PATH",
echo puis double-clique a nouveau sur ce fichier.
start "" https://www.python.org/downloads/
pause
exit /b 1

:fail
echo.
echo Erreur pendant l'installation. Copie le message ci-dessus pour obtenir de l'aide.
pause
exit /b 1
