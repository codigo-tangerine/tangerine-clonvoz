# Prompt para instalar Tangerine Clonvoz con un agente

Copiá el bloque siguiente en Codex o Claude con acceso a tu terminal de Windows.

```text
Instalá y verificá Tangerine Clonvoz en esta PC usando el repositorio oficial
https://github.com/codigo-tangerine/tangerine-clonvoz o el ZIP oficial que te doy.

1. Inspeccioná README.md y los scripts antes de ejecutarlos. Confirmá Windows x64,
   Python 3.12 con Tkinter, FFmpeg en PATH, GPU NVIDIA y controlador compatible
   con CUDA 12.6. Si falta algo, indicá qué falta y usá una fuente oficial para
   instalarlo cuando tengas permiso. Evitá cambiar Python o el PATH global sin
   consultarme. Usá .venv dentro de la carpeta del proyecto.
2. Instalá torch y torchaudio 2.11.0 desde el índice CUDA 12.6 de PyTorch.
   Comprobá CUDA y BF16 nativo. Instalá requirements.txt y ejecutá pip check.
   Seguí INSTALAR EN WINDOWS.bat o ejecutá sus comandos individualmente para
   que el entorno y los errores queden visibles.
3. Ejecutá descargar_modelos.py en ese entorno. Descarga Qwen3-TTS 1.7B Base y
   Whisper Base desde Hugging Face. Informame que la primera descarga puede
   demorar y usar varios GB. Reutilizá la caché existente.
4. Iniciá servidor.py en 127.0.0.1:8791. Verificá HTTP 200 en /estudio/, /reels/ y
   /api/setup. Si el puerto está ocupado, identificá el proceso antes de actuar.
   Abrí http://127.0.0.1:8791/estudio/ y mantené el servidor disponible si te lo pedí.
5. Pedime una muestra de voz que tenga permiso de usar si quiero verificar
   transcripción y síntesis reales. Con esa referencia probá una toma breve
   y, para Reels, un diálogo piloto. Comprobá que el WAV se reproduce.
   Indicá qué pruebas completaste y cuáles quedaron pendientes.
6. Reportá la ruta de instalación y los enlaces locales. Conservá mis audios
   y resultados en esta PC. No los subas ni publiques cambios, no expongas
   el servidor a Internet y no des por probada la GPU solo porque abre la web.
```
