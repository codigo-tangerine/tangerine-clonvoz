import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8791"


def request(path, data=None, token=None):
    payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
    headers = {} if payload is None else {"Content-Type": "application/json", "X-Studio-Token": token}
    try:
        with urlopen(Request(BASE + path, payload, headers), timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            message = json.load(error).get("error")
        except (ValueError, AttributeError):
            message = None
        raise RuntimeError(message or f"El servidor respondió HTTP {error.code}.") from None


def main():
    parser = argparse.ArgumentParser(description="Generar diálogos por lote en el clonador local.")
    parser.add_argument("--listar-voces", action="store_true")
    parser.add_argument("--lote", help="Consultar un ID de lote de esta sesión del servidor.")
    parser.add_argument("--guion", type=Path)
    parser.add_argument("--voz")
    parser.add_argument("--salida", type=Path)
    parser.add_argument("--idioma", default="Spanish")
    parser.add_argument("--solo", nargs=2, action="append", metavar=("REEL", "ID"))
    parser.add_argument("--regenerar", action="store_true")
    args = parser.parse_args()
    if not (args.listar_voces or args.lote or (args.guion and args.voz and args.salida)):
        parser.error("Indicá --guion, --voz y --salida, o bien --listar-voces.")
    if args.regenerar and not args.solo:
        parser.error("--regenerar requiere --solo REEL ID para proteger el resto del lote.")
    if args.lote:
        print(json.dumps(request("/api/jobs/" + quote(args.lote, safe="")), ensure_ascii=False, indent=2))
        return 0
    setup = request("/api/setup")
    if args.listar_voces:
        for item in setup["references"]:
            print(f'{item["id"]}\t{item["name"]}\t{item["tone"]}\t{BASE}/audio/{quote(item["id"], safe="")}')
        return 0
    data = {"guion": json.loads(args.guion.read_text(encoding="utf-8-sig")), "voz": args.voz,
            "salida": str(args.salida.resolve()), "idioma": args.idioma, "regenerar": args.regenerar}
    if args.solo:
        data["solo"] = [{"reel": reel, "id": key} for reel, key in args.solo]
    job = request("/api/reels", data, setup["token"])
    key = job["id"]
    print(f'Lote {key}\nSalida: {job["salida"]}', flush=True)
    last = None
    while True:
        progress = request("/api/jobs/" + key)
        scenes = progress.get("manifest", {}).get("escenas", [])
        ready = sum(scene["estado"] == "listo" for scene in scenes)
        detail = (progress["message"], ready, len(scenes))
        if detail != last:
            print(f"{ready}/{len(scenes) or len(data['guion'])} listos · {progress['message']}", flush=True)
            last = detail
        if progress["state"] != "running":
            break
        time.sleep(.8)
    for scene in scenes:
        if scene["estado"] == "error":
            print(f'{scene["reel"]}/{scene["id"]}: {scene["error"]}', file=sys.stderr)
    for warning in progress.get("manifest", {}).get("avisos", []):
        print(warning)
    if scenes:
        print(Path(job["salida"]) / "manifiesto.json")
    return 0 if progress["state"] == "done" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
