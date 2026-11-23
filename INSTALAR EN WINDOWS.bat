@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHON=.venv\Scripts\python.exe"

py -3.12 -c "import struct, tkinter; assert struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 (
  echo Instala Python 3.12 de 64 bits con Tkinter desde python.org.
  goto error
)
ffmpeg -version >nul 2>&1
if errorlevel 1 (
  echo Instala FFmpeg, agrega su carpeta bin al PATH y vuelve a abrir el instalador.
  goto error
)
nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo Se requiere una GPU NVIDIA con el controlador instalado.
  goto error
)

if not exist "%PYTHON%" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto error
)
echo Instalando PyTorch para CUDA 12.6...
"%PYTHON%" -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu126
if errorlevel 1 goto error
"%PYTHON%" -c "import torch; assert torch.cuda.is_available(), 'CUDA no disponible'; assert torch.cuda.is_bf16_supported(including_emulation=False), 'La GPU no admite BF16 nativo'"
if errorlevel 1 goto error
echo Instalando dependencias...
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto error
"%PYTHON%" -m pip check
if errorlevel 1 goto error
echo Descargando Qwen3-TTS y Whisper Base. La primera vez puede demorar.
"%PYTHON%" descargar_modelos.py
if errorlevel 1 goto error
echo Instalacion terminada. Ejecuta ABRIR CLONADOR WEB.bat.
pause
exit /b 0

:error
echo Instalacion interrumpida. Revisa el mensaje anterior y vuelve a ejecutar este archivo.
pause
exit /b 1
