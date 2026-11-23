@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta INSTALAR EN WINDOWS.bat.
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
set "HF_HUB_OFFLINE=1"
echo Abri Tangerine Clonvoz en http://127.0.0.1:8791/estudio/
".venv\Scripts\python.exe" servidor.py
