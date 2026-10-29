"""Lo que comparten los tests: dónde está el repo, cargar MidiRouter.py sin Live y un entorno de Live de mentira."""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "Ableton" / "CustomMaschineMK3"
for ruta in (RAIZ, RAIZ / "tools"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))


def cargar_router():
    spec = importlib.util.spec_from_file_location("MidiRouter", SCRIPT / "MidiRouter.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class Entorno:
    """Lo que el router le pregunta a Live (y note_repeat_open, que mira el script antes de cerrar el selector)."""

    def __init__(self, **valores):
        self.shift_pressed = self.solo_pressed = self.erase_pressed = False
        self.mute_pressed = self.macro_pressed = self.plugin_pressed = False
        self.encoder_tempo_mode = False
        self.display_mode = "default"
        self.encoder_mode = "default"
        self.note_repeat_open = False
        for nombre, valor in valores.items():
            setattr(self, nombre, valor)
