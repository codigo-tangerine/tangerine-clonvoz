import ctypes
import json
import os
import queue
import random
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import winsound
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
LIBRARY = ROOT / "referencias"
OUTPUT = ROOT / "resultados"
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
SEED = 1005916600
LANGUAGES = ("Spanish", "English", "Portuguese", "French", "Italian", "German",
             "Chinese", "Japanese", "Korean", "Russian", "Auto")

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["PYTHONUTF8"] = "1"


def references():
    for folder in (LIBRARY,):
        for path in sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            with path.open(encoding="utf-8-sig") as handle:
                item = json.load(handle)
            wav = Path(item.get("wav_path") or "")
            if not wav.is_file():
                wav = path.with_suffix(".wav")
            if wav.is_file() and item.get("transcript"):
                yield item, wav


def load_clone_model(status):
    import torch
    from huggingface_hub import snapshot_download
    from qwen_tts import Qwen3TTSModel

    if not torch.cuda.is_available():
        raise RuntimeError("El entorno de Qwen no detectó una GPU CUDA.")
    status("Cargando Qwen3-TTS 1.7B…")
    snapshot = snapshot_download(MODEL_ID, local_files_only=True)
    return Qwen3TTSModel.from_pretrained(
        snapshot, device_map="cuda:0", dtype=torch.bfloat16, local_files_only=True
    )
def synthesize(text, language, wav, transcript, destination, status):
    import soundfile as sf
    import torch

    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    model = load_clone_model(status)
    status("Generando el audio…")
    audio, rate = model.generate_voice_clone(
        text=text, language=language, ref_audio=str(wav), ref_text=transcript
    )
    sf.write(destination, audio[0], rate)


def mci(command):
    driver = ctypes.windll.winmm
    code = driver.mciSendStringW(command, None, 0, None)
    if code:
        message = ctypes.create_unicode_buffer(256)
        driver.mciGetErrorStringW(code, message, len(message))
        raise RuntimeError(message.value)


class VoiceApp:
    def __init__(self, window):
        self.window = window
        window.title("Clonador de voz")
        window.geometry("1080x740")
        window.minsize(840, 660)
        window.configure(bg="#f5f3ff")
        self.presets = json.loads((ROOT / "lecturas.json").read_text(encoding="utf-8-sig"))
        self.labels = {item["label"]: item for item in self.presets}
        self.script_index = 0
        self.wav = self.result = None
        self.recording = False
        self.events = queue.Queue()
        self.ref_label = tk.StringVar(value="Elegí cómo querés aportar tu muestra.")
        self.hint = tk.StringVar()
        self.status = tk.StringVar(value="Tu voz se procesa en este equipo.")
        self.step = 0

        style = ttk.Style(window)
        style.theme_use("clam")
        style.configure("TCombobox", padding=8, font=("Segoe UI", 10),
                        foreground="#302449", fieldbackground="#f7f4fd", bordercolor="#e1d8f3")
        style.map("TCombobox", fieldbackground=[("readonly", "#f7f4fd")],
                  foreground=[("readonly", "#302449")])
        body = tk.Frame(window, bg="#f5f3ff", padx=32, pady=23)
        body.pack(fill="both", expand=True)
        header = tk.Frame(body, bg="#f5f3ff")
        header.pack(fill="x", pady=(0, 18))
        self.label(header, "Clonador de voz", 26, bold=True, bg="#f5f3ff").pack(side="left")
        self.label(header, "●  Qwen3-TTS 1.7B · Local", 10, color="#5d4393",
                   bg="#eae0ff", padx=13, pady=7).pack(side="right")

        flow = tk.Frame(body, bg="#f5f3ff")
        flow.pack(fill="x", pady=(0, 16))
        self.tabs = []
        for index, title in enumerate(("01   Elegí tu voz", "02   Escribí el texto", "03   Escuchá el clon")):
            flow.columnconfigure(index, weight=1, uniform="flow")
            tab = self.button(flow, title, lambda step=index: self.show(step))
            tab.grid(row=0, column=index, sticky="ew", padx=(0 if not index else 5, 0))
            self.tabs.append(tab)

        main = tk.Frame(body, bg="#f5f3ff")
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        self.pages = []
        for _ in range(3):
            page = tk.Frame(main, bg="white", padx=24, pady=19,
                            highlightbackground="#e6def4", highlightthickness=1)
            page.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
            self.pages.append(page)
        side = tk.Frame(main, bg="#ebe2ff", width=248, padx=17, pady=18)
        side.grid(row=0, column=1, sticky="ns")
        side.pack_propagate(False)
        self.illustration = tk.Canvas(side, width=212, height=162, bg="#ebe2ff", highlightthickness=0)
        self.illustration.pack(fill="x", pady=(10, 12))
        self.side_title = self.label(side, "", 17, bold=True, bg="#ebe2ff", wraplength=210)
        self.side_title.pack(anchor="w")
        self.side_copy = self.label(side, "", 11, color="#594571", bg="#ebe2ff", wraplength=205)
        self.side_copy.pack(anchor="w", pady=8)
        self.side_status = self.label(side, "", 10, color="#614891", bg="#ebe2ff", wraplength=200)
        self.side_status.pack(side="bottom", anchor="w")

        ref, target, result = self.pages
        self.label(ref, "Tu voz de referencia", 21, bold=True).pack(anchor="w")
        row = tk.Frame(ref, bg="white")
        row.pack(fill="x", pady=(8, 6))
        self.record = self.button(row, "●  Grabar lectura", self.toggle_record, primary=True)
        self.record.pack(side="left")
        self.upload = self.button(row, "Abrir audio", self.open_audio)
        self.upload.pack(side="left", padx=6)
        self.button(row, "▶  Escuchar", lambda: self.play(self.wav)).pack(side="left")
        self.button(row, "Guardar", self.save_reference).pack(side="left", padx=6)
        self.saved = ttk.Combobox(ref, state="readonly")
        self.saved.pack(fill="x")
        self.saved.bind("<<ComboboxSelected>>", self.choose_saved)
        self.label(ref, variable=self.ref_label, size=9, color="#654e81", wraplength=480).pack(anchor="w", pady=(4, 8))
        row = tk.Frame(ref, bg="white")
        row.pack(fill="x")
        self.tone = ttk.Combobox(row, state="readonly", values=list(self.labels), width=29)
        self.tone.current(0)
        self.tone.pack(side="left")
        self.tone.bind("<<ComboboxSelected>>", self.change_tone)
        self.button(row, "Usar ejemplo", self.use_example).pack(side="left", padx=6)
        self.label(ref, variable=self.hint, size=9, color="#654e81", wraplength=505).pack(anchor="w", pady=(5, 6))
        self.label(ref, "Transcripción exacta de tu muestra", 10, bold=True).pack(anchor="w")
        self.transcript = self.editor(ref, 4)
        self.transcript.pack(fill="both", expand=True, pady=(4, 8))
        self.button(ref, "Continuar al texto  →", lambda: self.show(1), primary=True).pack(anchor="e")
        self.change_tone()

        self.label(target, "¿Qué querés decir?", 21, bold=True).pack(anchor="w")
        self.label(target, "Escribí el texto que va a decir la voz clonada.", 11,
                   color="#654e81").pack(anchor="w", pady=(3, 15))
        self.text = self.editor(target, 8)
        self.text.pack(fill="both", expand=True)
        row = tk.Frame(target, bg="white")
        row.pack(fill="x", pady=(12, 0))
        self.label(row, "Idioma", 10, bold=True).pack(side="left")
        self.language = ttk.Combobox(row, state="readonly", values=LANGUAGES, width=12)
        self.language.current(0)
        self.language.pack(side="left", padx=8)
        self.generate = self.button(row, "✦  Generar mi voz", self.start, primary=True)
        self.generate.pack(side="right")

        self.label(result, "Tu voz clonada", 21, bold=True).pack(anchor="w")
        self.result_title = self.label(result, "Tu audio aparecerá acá", 13, color="#654e81", wraplength=460)
        self.result_title.pack(anchor="w", pady=(5, 12))
        self.wave = tk.Canvas(result, height=144, bg="#f2ebff", highlightthickness=0)
        self.wave.pack(fill="x")
        self.wave.bind("<Configure>", self.draw_wave)
        self.progress = ttk.Progressbar(result, mode="indeterminate")
        row = tk.Frame(result, bg="white")
        row.pack(fill="x", pady=15)
        self.play_result = self.button(row, "▶  Escuchar", lambda: self.play(self.result), primary=True)
        self.play_result.config(state="disabled")
        self.play_result.pack(side="left")
        self.save_result = self.button(row, "Guardar WAV", self.export)
        self.save_result.config(state="disabled")
        self.save_result.pack(side="left", padx=7)
        self.button(row, "Abrir carpeta", lambda: os.startfile(OUTPUT)).pack(side="left")
        self.button(result, "←  Volver al texto", lambda: self.show(1)).pack(side="bottom", anchor="w")

        self.label(body, variable=self.status, size=10, color="#514065", bg="#f5f3ff",
                   wraplength=760).pack(anchor="w", pady=(10, 0))
        self.refresh()
        if self.items:
            self.saved.current(0)
            self.choose_saved()
        self.show(0)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(120, self.poll)

    @staticmethod
    def label(parent, text="", size=11, *, variable=None, color="#29203f", bg="white", bold=False, **options):
        return tk.Label(parent, text=text, textvariable=variable, fg=color, bg=bg,
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        anchor="w", justify="left", **options)

    @staticmethod
    def button(parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, relief="flat", bd=0, padx=12, pady=8,
                         font=("Segoe UI", 10, "bold"), cursor="hand2", disabledforeground="#9b90aa",
                         bg="#6a41cb" if primary else "#f0e8ff", fg="white" if primary else "#493278",
                         activebackground="#5432ac" if primary else "#e5d7ff",
                         activeforeground="white" if primary else "#352362")

    @staticmethod
    def editor(parent, rows):
        return tk.Text(parent, wrap="word", height=rows, font=("Segoe UI", 11), undo=True,
                       bg="#f8f5fd", fg="#29203f", padx=12, pady=10, relief="flat",
                       highlightthickness=1, highlightbackground="#e8dff6", highlightcolor="#7955d1")

    def show(self, step):
        self.step = step
        self.pages[step].tkraise()
        for index, tab in enumerate(self.tabs):
            tab.config(bg="#6943c2" if index == step else "#ebe2ff",
                       fg="white" if index == step else "#543a86")
        title, copy, detail = (
            ("La intención empieza en tu voz", "Leé el ejemplo con el tono que querés. También podés elegir una muestra que ya tenga esa intención.", "Muestra y transcripción"),
            ("Tu voz, nuevas palabras", "El guion define qué se dice. La grabación de referencia guía cómo suena.", "Texto e idioma"),
            ("Escuchá el resultado", "Reproducí tu clon y guardalo en WAV para usarlo donde quieras.", "Reproductor y exportación"),
        )[step]
        self.side_title.config(text=title)
        self.side_copy.config(text=copy)
        self.side_status.config(text=detail)
        art = self.illustration
        art.delete("all")
        art.create_oval(30, 5, 182, 157, fill="#dfceff", outline="")
        art.create_oval(47, 22, 165, 140, fill="#f8f2ff", outline="white", width=2)
        for x, y in ((27, 43), (174, 25), (179, 128), (43, 131)):
            art.create_text(x, y, text="✦", fill="#9873e0", font=("Segoe UI", 15))
        for index, height in enumerate(([18, 40, 70, 49, 25], [28, 49, 34, 56, 26], [19, 34, 63, 44, 23])[step]):
            x = 74 + index * 16
            art.create_line(x, 81-height/2, x, 81+height/2, fill=("#a079e8", "#8050d5", "#6a3dc0", "#8757d9", "#ad8bea")[index],
                            width=7, capstyle="round")

    def draw_wave(self, _event=None):
        canvas = self.wave
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        peaks = getattr(self, "peaks", [])
        count = len(peaks) or 48
        for index in range(count):
            x = 16 + (width - 32) * (index + 0.5) / count
            bar = 3 + (peaks[index] * height * 0.40 if peaks else 0)
            canvas.create_line(x, height / 2 - bar, x, height / 2 + bar,
                               width=3, capstyle="round", fill="#8555dc" if peaks else "#cbb8ef")
    def refresh(self):
        self.items = list(references())
        self.saved["values"] = [
            f'{item.get("original_filename") or wav.name}  ·  {item.get("capture_intent") or "sin etiqueta"}  ·  {wav.stem}'
            for item, wav in self.items
        ]

    def fill_transcript(self, value):
        self.transcript.delete("1.0", "end")
        self.transcript.insert("1.0", value)

    def select_audio(self, wav):
        self.wav = wav
        self.ref_label.set(wav.name)

    def choose_saved(self, _event=None):
        index = self.saved.current()
        if self.recording or index < 0:
            return
        item, wav = self.items[index]
        self.select_audio(wav)
        self.fill_transcript(item["transcript"])

    def change_tone(self, _event=None):
        self.script_index = 0
        preset = self.labels[self.tone.get()]
        self.hint.set(preset["hint"] + " Leé el ejemplo o escribí tu propio guion para grabar.")

    def use_example(self):
        current = self.transcript.get("1.0", "end-1c").strip()
        if current and not messagebox.askyesno("Usar ejemplo", "¿Reemplazar el texto de la referencia por una lectura de ejemplo?"):
            return
        scripts = self.labels[self.tone.get()]["scripts"]
        self.wav = None
        self.saved.set("")
        self.ref_label.set("Lectura de ejemplo pendiente de grabar.")
        self.fill_transcript(scripts[self.script_index % len(scripts)])
        self.script_index += 1
        self.status.set("Grabá esta lectura con la intención elegida.")

    def open_audio(self):
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.wav *.mp3 *.ogg *.webm *.flac *.m4a")])
        if not path:
            return
        self.select_audio(Path(path))
        self.saved.set("")
        self.fill_transcript("")

    def toggle_record(self):
        try:
            if not self.recording:
                winsound.PlaySound(None, 0)
                mci("open new type waveaudio alias voiceref")
                try:
                    mci("record voiceref")
                except RuntimeError:
                    mci("close voiceref")
                    raise
                self.recording = True
                self.record.config(text="Detener grabación")
                self.status.set("Grabando desde el micrófono predeterminado…")
                return
            wav = LIBRARY / datetime.now().strftime("voz_%Y%m%d_%H%M%S_%f.wav")
            try:
                mci("stop voiceref")
                mci(f'save voiceref "{wav}"')
            finally:
                self.recording = False
                self.record.config(text="Grabar con micrófono")
                mci("close voiceref")
            self.select_audio(wav)
            self.saved.set("")
            self.status.set("Grabación lista. Revisá que la transcripción coincida con lo que dijiste.")
        except RuntimeError as error:
            messagebox.showerror("Micrófono", str(error))

    def normalize(self, source, target):
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
             "-ac", "1", "-ar", "24000", str(target)],
            check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )

    def save_reference(self):
        if self.recording:
            return
        transcript = self.transcript.get("1.0", "end-1c").strip()
        if not self.wav or not transcript:
            messagebox.showwarning("Referencia", "Necesitás un audio y su transcripción exacta.")
            return
        name = datetime.now().strftime("referencia_%Y%m%d_%H%M%S_%f")
        wav = LIBRARY / f"{name}.wav"
        try:
            self.normalize(self.wav, wav)
        except (OSError, subprocess.CalledProcessError) as error:
            messagebox.showerror("Guardar referencia", str(getattr(error, "stderr", None) or error))
            return
        wav.with_suffix(".json").write_text(json.dumps({
            "original_filename": self.wav.name, "transcript": transcript,
            "capture_intent": self.labels[self.tone.get()]["label"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        self.refresh()
        self.saved.current(0)
        self.choose_saved()
        self.status.set("Referencia guardada.")

    def start(self):
        if self.recording:
            messagebox.showwarning("Grabación", "Detené la grabación antes de generar.")
            return
        text = self.text.get("1.0", "end-1c").strip()
        transcript = self.transcript.get("1.0", "end-1c").strip()
        if not (self.wav and self.wav.is_file() and transcript and text):
            messagebox.showwarning("Faltan datos", "Elegí el audio de referencia, revisá su transcripción y escribí el texto a generar.")
            return
        wav, language = self.wav, self.language.get()
        result = OUTPUT / datetime.now().strftime("clon_%Y%m%d_%H%M%S_%f.wav")
        self.generate.config(state="disabled")
        self.show(2)
        self.result_title.config(text="Preparando tu clon…")
        self.progress.pack(fill="x", pady=6, after=self.wave)
        self.progress.start(12)
        self.play_result.config(state="disabled")
        self.save_result.config(state="disabled")
        self.status.set("Preparando la referencia…")

        def run():
            from tempfile import TemporaryDirectory
            try:
                with TemporaryDirectory(prefix="voz_") as directory:
                    normalized = Path(directory) / "ref.wav"
                    self.normalize(wav, normalized)
                    synthesize(text, language, normalized, transcript, result,
                               lambda value: self.events.put(("status", value)))
                self.events.put(("done", result))
            except Exception as error:
                self.events.put(("error", str(getattr(error, "stderr", None) or error)))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == "status":
                self.status.set(value)
                continue
            self.progress.stop()
            self.progress.pack_forget()
            self.generate.config(state="normal")
            if kind == "error":
                self.status.set("La generación falló.")
                self.result_title.config(text="Podés volver al texto e intentar de nuevo.")
                if self.result:
                    self.play_result.config(state="normal")
                    self.save_result.config(state="normal")
                messagebox.showerror("Qwen3-TTS", value)
                continue
            import numpy as np
            import soundfile as sf

            self.result = value
            samples, rate = sf.read(value, dtype="float32")
            chunks = np.array_split(np.abs(samples), 64)
            self.peaks = [float(chunk.max()) if chunk.size else 0 for chunk in chunks]
            self.draw_wave()
            self.result_title.config(text=f"Audio listo · {len(samples) / rate:.1f} s · WAV")
            self.status.set(f"Audio listo · {value.name}")
            self.play_result.config(state="normal")
            self.save_result.config(state="normal")
        self.window.after(120, self.poll)

    def play(self, wav):
        if not wav or self.recording:
            return
        if wav.suffix.lower() != ".wav":
            os.startfile(wav)
        else:
            winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC)

    def export(self):
        destination = filedialog.asksaveasfilename(
            defaultextension=".wav", initialfile=self.result.name, filetypes=[("Audio WAV", "*.wav")]
        )
        if destination and Path(destination).resolve() != self.result.resolve():
            shutil.copyfile(self.result, destination)

    def close(self):
        if self.recording:
            mci("close voiceref")
        self.window.destroy()


if __name__ == "__main__":
    LIBRARY.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)
    if "--verificar" in sys.argv:
        item, wav = next(references())
        synthesize("Hola. Esta es una prueba del clonador de voz.", "Spanish", wav,
                   item["transcript"], OUTPUT / "prueba.wav", print)
    else:
        window = tk.Tk()
        VoiceApp(window)
        window.mainloop()
