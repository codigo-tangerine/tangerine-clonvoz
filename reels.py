import hashlib
import json
import math
import random
import re
from pathlib import Path, PurePosixPath
from uuid import uuid4

from clonador import MODEL_ID, SEED, load_clone_model

SCHEME = 1
PARTS = re.compile(r"^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*$")
WINDOWS_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path, data):
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def scenes_for(source, root):
    if not isinstance(source, list) or not 1 <= len(source) <= 250:
        raise ValueError("El guion debe ser una lista de 1 a 250 diálogos.")
    keys, paths, result = set(), set(), []
    for number, item in enumerate(source, 1):
        try:
            reel, key, text = str(item["reel"]), str(item["id"]), item["texto"]
            raw_path = item["archivo"]
            path = PurePosixPath(raw_path)
            start, duration = float(item["inicio"]), float(item["duracion"])
        except (TypeError, KeyError, ValueError, OverflowError):
            raise ValueError(f"Diálogo {number}: faltan campos válidos.") from None
        if not (reel.strip() and key.strip() and isinstance(text, str) and text.strip() and len(text) <= 5000):
            raise ValueError(f"Diálogo {number}: revisá reel, id y texto (hasta 5000 caracteres).")
        if not (math.isfinite(start) and math.isfinite(duration) and start >= 0 and duration >= 0):
            raise ValueError(f"Diálogo {number}: tiempos de montaje inválidos.")
        if not path.parts or path.suffix.lower() != ".wav" or any(
            not PARTS.fullmatch(part) or WINDOWS_RESERVED.match(part) for part in raw_path.split("/")
        ):
            raise ValueError(f"Diálogo {number}: archivo WAV relativo inválido: {raw_path}")
        destination = root.joinpath(*path.parts).resolve()
        if not destination.is_relative_to(root):
            raise ValueError(f"Diálogo {number}: el destino sale de la carpeta de salida.")
        unique = path.as_posix().casefold()
        if (reel, key) in keys or unique in paths:
            raise ValueError(f"Diálogo {number}: clave (reel, id) o ruta repetida.")
        keys.add((reel, key))
        paths.add(unique)
        result.append(dict(reel=item["reel"], id=key, texto=text, inicio=start,
                           duracion=duration, archivo=path.as_posix()))
    return result


def marks_for(text, audio, rate):
    import numpy as np

    # Approximate only. Use the active audio span and distribute it by word length and punctuation.
    words = re.findall(r"\S+", text)
    magnitude = np.abs(audio)
    active = np.flatnonzero(magnitude > max(.006, float(magnitude.max()) * .035))
    start = float(active[0] / rate) if len(active) else 0
    end = float((active[-1] + 1) / rate) if len(active) else len(audio) / rate
    weights = [max(2, sum(ch.isalnum() for ch in word)) +
               (3 if word.endswith((".", "!", "?", "…")) else 1 if word.endswith((",", ";", ":")) else 0)
               for word in words]
    total, elapsed = sum(weights), 0
    result = []
    for word, weight in zip(words, weights):
        next_elapsed = elapsed + weight
        result.append({"palabra": word, "inicio": round(start + (end - start) * elapsed / total, 4),
                       "fin": round(start + (end - start) * next_elapsed / total, 4)})
        elapsed = next_elapsed
    return result


def timing_warnings(entries):
    reels = {}
    for entry in entries:
        if entry.get("estado") == "listo":
            reels.setdefault(str(entry["reel"]), []).append(entry)
    warnings = []
    for reel, items in reels.items():
        hook = next((item for item in items if item["id"] == "hook"), None)
        title = next((item for item in items if re.match(r"^parte\s+\w+", item["texto"].lstrip(), re.I)), None)
        if hook and title and len(title["palabras"]) >= 2:
            title_start = max(title["inicio"], hook["inicio"] + hook["duracion_real"])
            number_end = title_start + title["palabras"][1]["fin"]
            if number_end > 5:
                warnings.append(f"Reel {reel}: la pregunta y el arranque dejan el número de parte "
                                f"cerca de {number_end:.2f} s (estimado). Revisá el montaje para anunciarlo antes de 5 s.")
    return warnings


def render(job_id, root, scenes, voice, reference, wav, language, targets, force, publish):
    path = root / "manifiesto.json"
    root.mkdir(parents=True, exist_ok=True)
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if previous and previous.get("version") != SCHEME:
        raise ValueError("La carpeta contiene un manifiesto ajeno o incompatible. Elegí otra carpeta.")
    indexed = {}
    for item in previous.get("escenas", []):
        pending = item.get("audio_nuevo")
        if pending:
            recover = root.joinpath(*PurePosixPath(item["archivo"]).parts).resolve()
            if recover.is_relative_to(root) and recover.is_file() and file_digest(recover) == pending["sha256"]:
                item = {**item, **pending, "estado": "listo"}
        indexed[item["archivo"].casefold()] = item
    # Pilot / partial retry keeps every other previously exported scene in the manifest.
    manifest = {"version": SCHEME, "lote": job_id, "modelo": MODEL_ID, "voz": voice,
                "idioma": language, "semilla": SEED, "escenas": [], "avisos": [],
                "marcas_palabra": "estimadas sobre la señal y el texto; sin alineador"}
    voice_hash = fingerprint([voice, file_digest(wav), reference["transcript"], MODEL_ID, SEED, language])
    model = prompt = None
    entries = manifest["escenas"]
    for scene in scenes:
        old = indexed.get(scene["archivo"].casefold())
        path = root.joinpath(*PurePosixPath(scene["archivo"]).parts).resolve()
        signature = fingerprint([voice_hash, scene["reel"], scene["id"], scene["texto"]])
        requested = targets is None or (str(scene["reel"]), scene["id"]) in targets
        owned = bool(old and old.get("estado") == "listo" and path.is_file()
                     and old.get("sha256") == file_digest(path))
        cached = owned and old.get("huella") == signature
        if cached and (not force or not requested):
            entries.append({**old, **scene, "reutilizado": True})
        elif not requested:
            entries.append({**scene, "estado": "pendiente", "anterior": old if owned else None})
        else:
            entries.append({**scene, "estado": "en cola", "anterior": old if owned else None})
    path = root / "manifiesto.json"
    for entry in entries:
        # Recover the previous ownership record even after interrupted attempts.
        if entry.get("anterior"):
            old_owned = entry["anterior"]
            entry["audio_anterior"] = {"sha256": old_owned["sha256"]}
        old_meta = indexed.get(entry["archivo"].casefold(), {})
        if not entry.get("audio_anterior") and old_meta.get("audio_anterior"):
            entry["audio_anterior"] = old_meta["audio_anterior"]
        entry.pop("anterior", None)

    def flush():
        manifest["avisos"] = timing_warnings(entries)
        atomic_json(path, manifest)
        publish(manifest)

    flush()
    for index, entry in enumerate(entries):
        if entry["estado"] != "en cola":
            continue
        destination = root.joinpath(*PurePosixPath(entry["archivo"]).parts).resolve()
        temp = destination.with_name(f".{destination.stem}.{uuid4().hex}.wav")
        entry["estado"] = "generando"
        publish(manifest)
        try:
            if not destination.is_relative_to(root):
                raise ValueError("El destino sale de la carpeta de salida.")
            if destination.exists() and entry.get("audio_anterior", {}).get("sha256") != file_digest(destination):
                raise ValueError("El destino ya existe y no pertenece a este lote.")
            if model is None:
                import soundfile as sf
                import torch

                model = load_clone_model(lambda message: publish(manifest, message))
                prompt = model.create_voice_clone_prompt(ref_audio=str(wav), ref_text=reference["transcript"])
            random.seed(SEED)
            torch.manual_seed(SEED)
            torch.cuda.manual_seed_all(SEED)
            audio, rate = model.generate_voice_clone(text=entry["texto"], language=language,
                                                     voice_clone_prompt=prompt)
            signal = audio[0]
            if not len(signal) or float(abs(signal).max()) <= .001:
                raise ValueError("El modelo no devolvió señal audible.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            sf.write(temp, signal, rate, format="WAV")
            checksum = file_digest(temp)
            words = marks_for(entry["texto"], signal, rate)
            metadata = dict(duracion_real=len(signal) / rate, frecuencia=rate, palabras=words,
                            huella=fingerprint([voice_hash, entry["reel"], entry["id"], entry["texto"]]),
                            sha256=checksum, reutilizado=False)
            entry["audio_nuevo"] = metadata
            flush()
            temp.replace(destination)
            entry.pop("audio_anterior", None)
            entry.pop("audio_nuevo", None)
            entry.update(estado="listo", **metadata)
        except Exception as error:
            entry.update(estado="error", error=str(error))
        finally:
            temp.unlink(missing_ok=True)
        flush()
    return manifest
