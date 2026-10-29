"""Recibe de VirtualDJ el estado de cada deck.

VirtualDJ lo manda al puerto MIDI virtual "MK3 Screens" como un controlador más
(vdj/generar.py): textos por sysex F0 7D <campo> <texto> F7, con campo = deck * 16 +
código (ver FIELDS en vdj/generar.py), cada uno cuando cambia.

El puerto lo crea vdj_puerto.py, un proceso aparte que no se reinicia con el
prototipo: si el puerto desapareciera, VirtualDJ no se reconecta hasta reiniciarlo.
vdj_puerto.py pasa cada sysex por UDP a este módulo y guarda el último valor de cada
campo, así un prototipo recién arrancado pide todo y no espera a que algo cambie.
"""

import socket
import threading
from pathlib import Path

from paths import DATA_DIR
import time
import unicodedata

SYSEX_ID = 0x7D  # "uso no comercial / experimental"
BRIDGE_ADDRESS = ("127.0.0.1", 9018)  # vdj_puerto.py: acá se le piden todos los valores
DATA_PORT = 9019  # vdj_puerto.py manda acá cada sysex (sin F0 / F7)
REQUEST_ALL = b"todo"
REPLAY_MARK = 0x52  # "R": vdj_puerto.py reenvía un valor guardado (no es un dato nuevo de VirtualDJ)
PORT_STARTED_FILE = DATA_DIR / "vdj_puerto.started"


def port_started():
    """Hora (time.time) en que vdj_puerto.py creó el puerto, o None."""
    try:
        return float(PORT_STARTED_FILE.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None

FIELDS = {
    1: "title", 2: "artist", 3: "bpm", 4: "bpm_original", 5: "playing", 6: "volume", 7: "filter",
    8: "sync", 9: "pitch_lock", 10: "loop", 11: "loop_length", 12: "title_utf8", 13: "artist_utf8", 14: "loaded",
    15: "position",
}
GLOBAL_FIELDS = {1: "encoder_mode", 2: "master_volume", 3: "headphone_volume", 4: "crossfader"}  # campo 0x3_
THOUSANDTHS = ("bpm", "bpm_original", "volume", "filter", "master_volume", "headphone_volume", "crossfader")
LOOP_LENGTHS = tuple(2.0 ** power for power in range(-5, 7))  # 1/32 ... 64 beats
FLAGS = ("playing", "pitch_lock", "loop", "loaded")

def _parse_loop(text):
    """Largo del loop en beats, al valor de la lista más cercano: VirtualDJ lo da como "4", "0.5" o "1/2"
    (y la versión anterior del mapeo, en milésimas sin multiplicar: 4 -> "4" llegaba como 0.004)."""
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            beats = float(numerator) / float(denominator)
        else:
            beats = float(text)
    except (ValueError, ZeroDivisionError):
        return None
    if beats <= 0:
        return None
    return min(LOOP_LENGTHS, key=lambda length: abs(length - beats) / length)


def _ascii_skeleton(text):
    return "".join(char if ord(char) < 127 else "?" for char in unicodedata.normalize("NFC", text))


class DeckState:
    def __init__(self):
        self.values = {}
        self.changed_at = {}  # campo -> perf_counter del último cambio (para los pop-ups)

    def get(self, name, default=None):
        return self.values.get(name, default)

    def _best_text(self, name):
        # El UTF-8 vale si llegó entero: en ASCII tiene que dar lo mismo que el campo ASCII
        ascii_text, utf8_text = self.values.get(name), self.values.get(name + "_utf8")
        if utf8_text and (ascii_text is None or _ascii_skeleton(utf8_text) == ascii_text):
            return utf8_text
        return ascii_text

    @property
    def title(self):
        return self._best_text("title")

    @property
    def artist(self):
        return self._best_text("artist")


class VdjData:
    def __init__(self):
        self.decks = [DeckState(), DeckState()]
        self.general = DeckState()  # encoder_mode ("0", "1" = VOLUME, "2" = SWING), master_volume, headphone_volume
        self.lock = threading.Lock()
        self.messages = 0
        self.last_live = time.time()  # último dato nuevo de VirtualDJ (no reenviado por vdj_puerto.py)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(("127.0.0.1", DATA_PORT))
        self._socket.settimeout(1.0)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _request_all(self):
        try:
            self._socket.sendto(REQUEST_ALL, BRIDGE_ADDRESS)
        except OSError:
            pass

    def _loop(self):
        self._request_all()
        last_request = time.perf_counter()
        while self._running:
            try:
                message, _ = self._socket.recvfrom(4096)
                self._handle(message)
            except (socket.timeout, ConnectionResetError):
                pass
            except OSError:
                if not self._running:
                    return
            # Si todavía no llegó nada (el puente arrancó después), se vuelve a pedir
            if not self.messages and time.perf_counter() - last_request > 2.0:
                self._request_all()
                last_request = time.perf_counter()

    def _handle(self, message):
        live = True
        if message[:1] == bytes([REPLAY_MARK]):
            live, message = False, message[1:]
        if live:
            self.last_live = time.time()
        if len(message) < 2 or message[0] != SYSEX_ID:
            return
        field = message[1]
        deck_index = (field >> 4) - 1
        name = (GLOBAL_FIELDS if deck_index == 2 else FIELDS).get(field & 0x0F)
        if deck_index not in (0, 1, 2) or name is None:
            return
        encoding = "utf-8" if name.endswith("_utf8") else "ascii"
        text = message[2:].decode(encoding, "replace").strip()
        if name in THOUSANDTHS:
            try:
                value = int(text) / 1000
            except ValueError:
                return
        elif name == "loop_length":
            value = _parse_loop(text)
            if value is None:
                return
        elif name in FLAGS:
            value = text == "1"
        else:
            value = text
        deck = self.general if deck_index == 2 else self.decks[deck_index]
        with self.lock:
            self.messages += 1
            if deck.values.get(name) != value:
                if name in deck.values:
                    deck.changed_at[name] = time.perf_counter()
                deck.values[name] = value

    def close(self):
        self._running = False
        self._socket.close()
