"""El tempo de VirtualDJ para Ableton (SHIFT + click del encoder en el modo TEMPO).

Elige el deck de referencia de VirtualDJ y le manda su BPM al script de Ableton por UDP, cada medio segundo. El
script guarda el último y, cuando se aprieta SHIFT + click, iguala el tempo de Live a ese número (sin Ableton Link:
Live no queda atado a lo que pase con los platos).

Deck de referencia:
  1. el que VirtualDJ marca como master (sync "M");
  2. si no hay, el que suena; si suenan los dos, el que se oye más (volumen x lado del crossfader);
  3. si no suena ninguno, el primero con un tema cargado;
  4. si no hay tema o VirtualDJ no está, nada (el script avisa que no hay tempo).
"""

import json
import socket
import time

SCRIPT_ADDRESS = ("127.0.0.1", 9021)  # en el script de Ableton: VDJ_TEMPO_ADDRESS
SEND_EVERY_SECONDS = 0.5


def _audible(index, volume, crossfader):
    # El crossfader va de 0 (deck 1) a 1 (deck 2): el lado de cada deck suena entero hasta el centro y se va apagando
    volume = 1.0 if volume is None else volume
    if crossfader is None:
        return volume
    side = min(1.0, (1.0 - crossfader) * 2.0) if index == 0 else min(1.0, crossfader * 2.0)
    return volume * side


def master_deck(vdj_data):
    """(índice del deck 0 o 1, BPM) del deck de referencia, o None si no hay ninguno."""
    with vdj_data.lock:
        decks = [(index, deck.get("bpm"), deck.get("playing"), deck.get("sync"), deck.get("volume"),
                  deck.get("loaded", True)) for index, deck in enumerate(vdj_data.decks)]
        crossfader = vdj_data.general.get("crossfader")
    candidates = [deck for deck in decks if deck[1] and deck[1] > 0]
    for index, bpm, _, sync, _, _ in candidates:
        if sync == "M":
            return index, bpm
    playing = [deck for deck in candidates if deck[2]]
    if playing:
        index, bpm, _, _, volume, _ = max(playing, key=lambda deck: _audible(deck[0], deck[4], crossfader))
        return index, bpm
    for index, bpm, _, _, _, loaded in candidates:
        if loaded:
            return index, bpm
    return None


class MasterBpmSender:
    def __init__(self, is_open=lambda: True):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._is_open = is_open  # si la ventana de VirtualDJ existe
        self._last = 0.0
        self.last_found = None  # (índice del deck, BPM) del último envío; la vista de tempo lo dibuja

    def maybe_send(self, vdj_data):
        now = time.perf_counter()
        if now - self._last < SEND_EVERY_SECONDS:
            return
        self._last = now
        found = master_deck(vdj_data) if vdj_data is not None and self._is_open() else None
        self.last_found = found
        message = {"t": time.time(), "bpm": round(found[1], 3) if found else None,
                   "deck": found[0] + 1 if found else None}
        try:
            self._socket.sendto(json.dumps(message).encode("ascii"), SCRIPT_ADDRESS)
        except OSError:
            pass  # el script no está escuchando (Ableton cerrado)

    def close(self):
        self._socket.close()
