"""Dónde viven los archivos del programa, suelto (python prototipo\\supervisor.py) o empaquetado (.exe).

- Suelto: los registros y el estado van a .venv\\ y la configuración a prototipo\\config.json.
- Empaquetado: todo va a %LOCALAPPDATA%\\MaschineMK3AsPush\\ (el programa puede estar en una carpeta sin permiso
  de escritura), y la primera vez se copia la configuración de ejemplo.
"""

import ctypes
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "MaschineMK3AsPush"
FROZEN = getattr(sys, "frozen", False)
CODE_DIR = Path(__file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", CODE_DIR))

# Cada proceso hijo es este mismo programa con una opción; suelto, es el script de siempre
_SCRIPTS = {"screens": "dj_screens.py", "port": "vdj_puerto.py"}


def _data_dir():
    if FROZEN:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME
    else:
        base = CODE_DIR.parent / ".venv"
    base.mkdir(parents=True, exist_ok=True)
    return base


DATA_DIR = _data_dir()


def config_path():
    if not FROZEN:
        return CODE_DIR / "config.json"
    target = DATA_DIR / "config.json"
    if not target.exists():
        shutil.copy2(BUNDLE_DIR / "config.example.json", target)
    return target


def child_command(name, windowless=False):
    """Comando para lanzar "screens" (las pantallas) o "port" (el puerto de datos de VirtualDJ)."""
    if FROZEN:
        return [sys.executable, f"--{name}"]
    scripts = CODE_DIR.parent / ".venv" / "Scripts"
    python = scripts / ("pythonw.exe" if windowless else "python.exe")
    return [str(python if python.exists() else sys.executable), "-u", str(CODE_DIR / _SCRIPTS[name])]


def message_box(text, title=APP_NAME):
    """Aviso en una ventana (el .exe no tiene consola)."""
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
    except Exception:
        print(text)
