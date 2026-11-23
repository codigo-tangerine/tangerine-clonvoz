@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero prepara el entorno siguiendo el README.
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
set "HF_HUB_OFFLINE=1"
".venv\Scripts\python.exe" servidor.py
