import argparse
import base64
import hmac
import json
import re
import ssl
import mimetypes
import shutil
import subprocess
import threading
from tempfile import TemporaryDirectory
from datetime import datetime
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from clonador import ROOT, LIBRARY, OUTPUT, LANGUAGES, references, synthesize

PORT = 8791
WEB = ROOT / "web"
DRAFTS = ROOT / "muestras-web"
LIMIT = 30 * 1024 * 1024
ORIGIN = f"http://127.0.0.1:{PORT}"
TOKEN = uuid4().hex
jobs = {}
batch_outputs = {}
lock = threading.Lock()


def normalize(data, destination):
    with TemporaryDirectory(prefix="voz_web_") as temp:
        upload = Path(temp) / "audio"
        upload.write_bytes(data)
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file,pipe,crypto,data",
             "-format_whitelist", "wav,mp3,mov,ogg,matroska,webm,flac,aac,amr",
             "-i", str(upload), "-t", "90", "-ac", "1", "-ar", "24000", str(destination)],
            capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )

def library():
    return {wav.stem: (item, wav) for item, wav in references()}


def source(key):
    saved = library().get(key)
    if saved:
        return saved[1]
    if len(key) == 32 and all(char in "0123456789abcdef" for char in key):
        candidate = DRAFTS / f"{key}.wav"
        if candidate.is_file():
            return candidate
    raise ValueError("Elegí una muestra de voz válida.")


def run_job(job, wav, payload, output):
    def update(message):
        with lock:
            job["message"] = message

    try:
        synthesize(payload["text"], payload["language"], wav, payload["transcript"], output, update)
        with lock:
            job.update(state="done", url=f"/result/{output.name}")
    except Exception as error:
        import traceback
        traceback.print_exc()
        with lock:
            job.update(state="error", message=str(error))


def run_transcript(job, wav, language):
    from transcriptor import transcribe

    try:
        text = transcribe(wav, language)
        if not text:
            raise ValueError("No encontré voz clara en esta muestra.")
        with lock:
            job.update(state="done", text=text)
    except Exception as error:
        import traceback
        traceback.print_exc()
        with lock:
            job.update(state="error", message=f"No se pudo transcribir la muestra. {error}")

def run_reels(key, job, output, scenes, voice, item, wav, language, targets, force):
    from reels import render

    def publish(manifest, message=None):
        with lock:
            job["manifest"] = deepcopy(manifest)
            job["message"] = message or "Procesando diálogos…"

    try:
        manifest = render(key, output, scenes, voice, item, wav, language, targets, force, publish)
        errors = sum(scene["estado"] == "error" for scene in manifest["escenas"])
        with lock:
            job.update(state="partial" if errors else "done",
                       message=f"{errors} diálogo(s) con error." if errors else "Lote terminado.")
    except Exception as error:
        with lock:
            job.update(state="error", message=str(error))

class Handler(BaseHTTPRequestHandler):
    def trusted_request(self):
        host = self.headers.get("Host")
        if host not in self.server.allowed_hosts:
            self.send_error(403)
            return False
        password = self.server.mobile_password
        if password:
            expected = "Basic " + base64.b64encode(f"voz:{password}".encode()).decode()
            actual = self.headers.get("Authorization", "")
            if not hmac.compare_digest(actual.encode(), expected.encode()):
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="Estudio de voz"')
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return False
        return True
    def send_bytes(self, content, kind, status=200):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, value, status=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self.trusted_request():
            return
        if path == "/api/setup":
            return self.send_json({
                "token": TOKEN, "languages": LANGUAGES,
                "tones": json.loads((ROOT / "lecturas.json").read_text(encoding="utf-8-sig")),
                "references": [
                    {"id": key, "name": item.get("original_filename") or wav.name,
                     "tone": item.get("capture_intent") or "", "transcript": item["transcript"]}
                    for key, (item, wav) in library().items()
                ],
            })
        if path.startswith("/api/jobs/"):
            with lock:
                job = jobs.get(path.rsplit("/", 1)[-1])
                result = dict(job) if job else None
            return self.send_json(result or {"error": "Generación no encontrada."}, 200 if result else 404)
        if path.startswith("/api/reels/audio/") and not self.server.mobile_password:
            _, _, _, _, key, number = path.split("/") if path.count("/") == 5 else ("", "", "", "", "", "")
            with lock:
                job = jobs.get(key, {})
                scenes = job.get("manifest", {}).get("escenas", [])
                root = batch_outputs.get(key)
                entry = scenes[int(number)] if number.isascii() and number.isdigit() and len(number) < 4 and int(number) < len(scenes) else None
            if root and entry and entry["estado"] == "listo":
                file = (root / entry["archivo"]).resolve()
                if file.is_relative_to(root) and file.is_file():
                    return self.send_bytes(file.read_bytes(), "audio/wav")
            return self.send_error(404)
        folder, _, name = path.rpartition("/")
        if folder == "/audio":
            try:
                file = source(unquote(name))
            except ValueError:
                return self.send_error(404)
        elif folder == "/result" and name.startswith("clon_web_") and name.endswith(".wav"):
            file = OUTPUT / name
        elif path == "/estudio/" and not self.server.mobile_password:
            file = ROOT / "demo" / "index.html"
        elif path == "/plantilla-reels.json":
            file = ROOT / "guion-ejemplo.json"
        elif path in ("/", "/studio.css", "/studio.js", "/voz.svg", "/mic-estudio.png", "/reels.js", "/reels.css", "/reels/"):
            file = WEB / ({"/": "index.html", "/reels/": "reels.html"}.get(path, name))
        else:
            return self.send_error(404)
        if not file.is_file():
            return self.send_error(404)
        self.send_bytes(file.read_bytes(), mimetypes.guess_type(file)[0] or "application/octet-stream")

    def do_POST(self):
        if not self.trusted_request():
            return
        if self.headers.get("X-Studio-Token") != TOKEN or self.headers.get("Origin") not in self.server.allowed_origins:
            return self.send_error(403)
        try:
            size = int(self.headers.get("Content-Length", 0))
            path = urlsplit(self.path).path
            if size <= 0 or size > (LIMIT if path == "/api/upload" else 128 * 1024):
                raise ValueError("Archivo vacío o demasiado grande. El máximo es 30 MB.")
            data = self.rfile.read(size)
            if path == "/api/upload":
                key = uuid4().hex
                wav = DRAFTS / f"{key}.wav"
                try:
                    normalize(data, wav)
                except subprocess.CalledProcessError:
                    wav.unlink(missing_ok=True)
                    raise ValueError("No pude leer ese audio. Probá con WAV, MP3, M4A, OGG o WebM.") from None
                return self.send_json({"id": key})
            payload = json.loads(data)
            if path == "/api/reels":
                if self.server.mobile_password:
                    return self.send_json({"error": "Reels está disponible en localhost."}, 403)
                return self.start_reels(payload)
            wav = source(payload["id"])
            if path == "/api/transcribe":
                language = payload.get("language", "Auto")
                if language not in LANGUAGES:
                    raise ValueError("Idioma de transcripción inválido.")
                key = uuid4().hex
                with lock:
                    if any(job.get("kind") == "transcript" and job["state"] == "running" for job in jobs.values()):
                        return self.send_json({"error": "Ya hay una transcripción en curso."}, 409)
                    job = jobs[key] = {"state": "running", "kind": "transcript", "message": "Transcribiendo la muestra…"}
                threading.Thread(target=run_transcript, args=(job, wav, language), daemon=True).start()
                return self.send_json({"id": key}, 202)
            transcript = payload.get("transcript", "").strip()
            if not transcript or len(transcript) > 12000:
                raise ValueError("Ingresá la transcripción exacta de la muestra.")
            if path == "/api/reference":
                label = payload.get("name", "").strip()[:80] or "Referencia de voz"
                stem = re.sub(r"[^\w -]+", "_", label).strip(" _-") or "Referencia"
                if re.fullmatch(r"CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9]", stem, re.I):
                    stem = "voz_" + stem
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                with lock:
                    destination = LIBRARY / f"{stem}.wav"
                    if any(destination.with_suffix(ext).exists() for ext in (".wav", ".txt", ".json")):
                        destination = LIBRARY / f"{stem} - {timestamp}.wav"
                    sidecar = destination.with_suffix(".txt")
                    metadata = destination.with_suffix(".json")
                    draft = metadata.with_suffix(".tmp")
                    try:
                        shutil.copyfile(wav, destination)
                        sidecar.write_text(transcript + "\n", encoding="utf-8")
                        draft.write_text(json.dumps({
                            "original_filename": label,
                            "capture_intent": str(payload.get("tone", ""))[:80],
                            "transcript": transcript,
                        }, ensure_ascii=False), encoding="utf-8")
                        draft.replace(metadata)
                    except OSError:
                        for file in (destination, sidecar, draft):
                            file.unlink(missing_ok=True)
                        raise
                return self.send_json({"id": destination.stem, "name": label,
                                       "audio": destination.name, "transcripcion": sidecar.name})
            if path != "/api/generate":
                return self.send_error(404)
            text = payload.get("text", "").strip()
            if not text or len(text) > 5000 or payload.get("language") not in LANGUAGES:
                raise ValueError("Ingresá hasta 5000 caracteres y elegí el idioma.")
            key = uuid4().hex
            with lock:
                if any(job.get("kind") != "transcript" and job["state"] == "running" for job in jobs.values()):
                    return self.send_json({"error": "Ya hay un clon en generación."}, 409)
                job = jobs[key] = {"state": "running", "message": "Preparando la muestra…"}
            filename = "clon_web_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".wav"
            threading.Thread(target=run_job, args=(job, wav, {
                "text": text, "language": payload["language"], "transcript": transcript,
            }, OUTPUT / filename), daemon=True).start()
            return self.send_json({"id": key}, 202)
        except (ValueError, KeyError, TypeError) as error:
            return self.send_json({"error": str(error)}, 400)
        except OSError:
            return self.send_json({"error": "No pude leer o guardar el audio en este equipo."}, 500)


    def start_reels(self, payload):
        from reels import scenes_for

        voice = payload.get("voz")
        saved = library().get(voice)
        if not saved:
            raise ValueError("Elegí explícitamente un ID de referencia guardada y escuchá la muestra.")
        language = payload.get("idioma", "Spanish")
        if language not in LANGUAGES:
            raise ValueError("Elegí un idioma válido.")
        raw = payload.get("salida")
        output = Path(raw) if raw else ROOT / "resultados-reels" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        if not output.is_absolute() or str(output).startswith(("\\\\", "//")):
            raise ValueError("La salida debe ser una carpeta local con ruta absoluta.")
        output = output.resolve()
        manifest_path = output / "manifiesto.json"
        if manifest_path.exists() and not manifest_path.resolve().is_relative_to(output):
            raise ValueError("El manifiesto sale de la carpeta de salida.")
        scenes = scenes_for(payload["guion"], output)
        targets = payload.get("solo")
        if targets is not None:
            if not isinstance(targets, list) or not targets:
                raise ValueError("Indicá al menos un diálogo para el piloto.")
            targets = {(str(item["reel"]), str(item["id"])) for item in targets}
            available = {(str(item["reel"]), item["id"]) for item in scenes}
            if not targets <= available:
                raise ValueError("El piloto incluye un diálogo ajeno al guion.")
        key = uuid4().hex
        with lock:
            if any(item.get("kind") != "transcript" and item["state"] == "running" for item in jobs.values()):
                return self.send_json({"error": "Ya hay una generación en curso. Volvé a intentar."}, 409)
            job = jobs[key] = {"kind": "reels", "state": "running", "message": "Preparando lote…",
                               "salida": str(output)}
            batch_outputs[key] = output
        item, wav = saved
        threading.Thread(target=run_reels, args=(key, job, output, scenes, voice, item, wav, language,
                                                targets, bool(payload.get("regenerar")),), daemon=True).start()
        return self.send_json({"id": key, "salida": str(output)}, 202)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--mobile-ip")
    parser.add_argument("--tls-dir", type=Path)
    args = parser.parse_args()
    for directory in (LIBRARY, OUTPUT, DRAFTS):
        directory.mkdir(exist_ok=True)
    if args.mobile_ip:
        host, port = args.mobile_ip, 8790
        scheme = "https"
        hosts = (f"{host}:{port}",)
    else:
        host, port, scheme = "127.0.0.1", args.port, "http"
        hosts = (f"127.0.0.1:{port}", f"localhost:{port}")
    with ThreadingHTTPServer((host, port), Handler) as server:
        server.allowed_hosts = hosts
        server.allowed_origins = (None, *(f"{scheme}://{name}" for name in hosts))
        server.mobile_password = None
        if args.mobile_ip:
            server.mobile_password = (args.tls_dir / "clave.txt").read_text(encoding="utf-8-sig").strip()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(args.tls_dir / "servidor.pem", args.tls_dir / "servidor.key")
            server.socket = context.wrap_socket(server.socket, server_side=True)
        print(f"Local: {scheme}://{host}:{port}", flush=True)
        if server.mobile_password:
            print(f"Usuario: voz | Clave: {server.mobile_password}", flush=True)
        server.serve_forever()
