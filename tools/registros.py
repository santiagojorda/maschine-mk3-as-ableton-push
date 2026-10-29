"""Junta los registros de todo el proyecto en una sola línea de tiempo, de más viejo a más nuevo.

Fuentes:
  - Live (Log.txt): solo las líneas del script de la Maschine y sus errores
  - el script de Ableton, detalle del marco (CustomMaschineMK3.log)
  - las pantallas y el supervisor (pantallas.log)
  - el puerto de datos de VirtualDJ (vdj_puerto.log)

Uso:  python tools/registros.py [minutos]     (por defecto, los últimos 10)
      python tools/registros.py 60 error       (solo las líneas que contengan "error", sin importar mayúsculas)
"""

import datetime
import glob
import os
import re
import sys
from pathlib import Path

LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", ""))
APPDATA = Path(os.environ.get("APPDATA", ""))
SCRIPT = Path(r"C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\Maschine_as_Push")
DATE = re.compile(r"^(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d)(\.\d+)?")


def live_log():
    candidates = glob.glob(str(APPDATA / "Ableton" / "Live *" / "Preferences" / "Log.txt"))
    return Path(max(candidates, key=os.path.getmtime)) if candidates else None


def sources():
    live = live_log()
    pairs = [
        ("live", live), ("script", SCRIPT / "CustomMaschineMK3.log"),
        ("pantallas", LOCALAPPDATA / "MaschineMK3AsPush" / "pantallas.log"),
        ("puerto", LOCALAPPDATA / "MaschineMK3AsPush" / "vdj_puerto.log"),
    ]
    # Suelto, con Python, el registro está en el .venv del proyecto
    venv = Path(__file__).resolve().parents[1] / "Pantallas" / ".venv"
    pairs += [("pantallas", venv / "pantallas.log"), ("puerto", venv / "vdj_puerto.log")]
    return [(name, path) for name, path in pairs if path is not None and path.exists()]


def entries(name, path):
    """(momento, fuente, texto): las líneas sin fecha (un error con su detalle) se pegan a la anterior."""
    current = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = DATE.match(line)
        if match:
            if current:
                yield current
            moment = datetime.datetime.fromisoformat(f"{match.group(1)} {match.group(2)}")
            current = [moment, name, line[match.end():].lstrip(": \t")]
        elif current:
            current[2] += "\n    " + line
    if current:
        yield current


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10
    needle = sys.argv[2].lower() if len(sys.argv) > 2 else None
    since = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
    rows = []
    for name, path in sources():
        for moment, source, text in entries(name, path):
            if moment < since:
                continue
            if name == "live" and "CustomMaschineMK3" not in text and "RemoteScriptError" not in text:
                continue
            if needle and needle not in text.lower():
                continue
            rows.append((moment, source, text))
    sys.stdout.reconfigure(encoding="utf-8")
    for moment, source, text in sorted(rows, key=lambda row: row[0]):
        print(f"{moment:%H:%M:%S} [{source:9}] {text}")
    if not rows:
        print(f"Nada en los últimos {minutes:g} minutos. Registros revisados: "
              f"{', '.join(str(path) for _, path in sources()) or 'ninguno'}")


if __name__ == "__main__":
    main()
