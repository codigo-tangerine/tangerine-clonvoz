# Tangerine Clonvoz

Clonador de voz local con transcripción editable y generación de un WAV por diálogo para Reels. El motor usa Qwen3-TTS 1.7B Base para clonar y Whisper Base para transcribir.

## Demo visual

Abrí [demo/index.html](demo/index.html) directamente en un navegador. La demo unificada simula las tomas y las descargas con sonidos de prueba. La interfaz conectada al motor está en `web/`.

## Ejecutar el motor local en Windows

El paquete de Windows incluye el código y un asistente que instala las dependencias de Python en un entorno local y descarga los modelos. Requiere Windows, Python 3.12 con Tkinter, FFmpeg disponible en el PATH y una GPU NVIDIA con un controlador compatible con CUDA 12.6 y BF16. Descargá Python y FFmpeg desde sus páginas oficiales.

- [Python](https://www.python.org/downloads/windows/)
- [FFmpeg](https://ffmpeg.org/download.html)
- [Paquetes CUDA de PyTorch](https://pytorch.org/get-started/previous-versions/)

1. Descargá el ZIP de [GitHub Releases](https://github.com/codigo-tangerine/tangerine-clonvoz/releases) cuando esté disponible o cloná este repositorio.
2. Extraé el ZIP en una carpeta donde tengas permiso de escritura y ejecutá `INSTALAR EN WINDOWS.bat`. La primera ejecución descarga varios GB.
3. Ejecutá `ABRIR CLONADOR WEB.bat` y abrí una de las direcciones locales indicadas abajo.

Si querés que Codex o Claude te ayude con la instalación, copiá el prompt de [README-AGENTES.md](README-AGENTES.md).

También podés ejecutar estos comandos desde PowerShell en la raíz del repositorio:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu126
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe descargar_modelos.py
& .\.venv\Scripts\python.exe servidor.py
```

Abrí [Tangerine Clonvoz](http://127.0.0.1:8791/estudio/) para usar ambos estudios con el motor local. Las rutas [Clonador individual](http://127.0.0.1:8791/) y [Diálogos para Reels](http://127.0.0.1:8791/reels/) también siguen disponibles. Después de la descarga inicial de modelos, el motor trabaja sin conexión. Las referencias, las transcripciones y los WAV quedan en la computadora.

### Reels por consola

Con el servidor corriendo, guardá una referencia en la biblioteca local y consultá su ID:

```powershell
& .\.venv\Scripts\python.exe generar-reels.py --listar-voces
$voz = Read-Host "ID de referencia"
& .\.venv\Scripts\python.exe generar-reels.py --guion guion-ejemplo.json --voz $voz --salida resultados-reels\ejemplo
```

Repetí el comando para reanudar en la misma carpeta. Agregá `--solo 1 hook --regenerar` para repetir un diálogo. La salida incluye WAV y un manifiesto con duraciones reales y marcas estimadas por palabra.

## Licencias

El código propio se publica con [licencia MIT](LICENSE). Las dependencias y los modelos conservan sus licencias. Los pesos se descargan desde sus repositorios oficiales y se almacenan en la caché local.

- [Qwen3-TTS 1.7B Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base), Apache 2.0.
- [Whisper Base](https://huggingface.co/openai/whisper-base), Apache 2.0 según la ficha del artefacto de Hugging Face.
