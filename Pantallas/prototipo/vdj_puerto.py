"""Mantiene el puerto MIDI virtual "MK3 Screens" por donde VirtualDJ manda el estado de los decks.

Corre aparte del prototipo (dj_screens.py lo lanza si no está) para que reiniciar el
prototipo no cierre el puerto: VirtualDJ no se reconecta a un puerto que desaparece
hasta que se reinicia. Pasa cada sysex por UDP a vdj_data.py y guarda el último de
cada campo: cuando el prototipo pide "todo", se los reenvía.

El puerto se abre sin que el driver arme los mensajes: el título en UTF-8 trae bytes
de 8 bits que cortarían un sysex, así que se juntan acá de F0 a F7.

Uso: python vdj_puerto.py   (si ya hay uno corriendo, este sale solo)
"""

import atexit
import logging
import os
import ctypes
import ctypes.wintypes as W
import faulthandler
import socket
import sys
import threading
import time
from pathlib import Path

import registro
from paths import DATA_DIR
from vdj_data import BRIDGE_ADDRESS, DATA_PORT, PORT_STARTED_FILE, REPLAY_MARK, REQUEST_ALL, SYSEX_ID

log = logging.getLogger("puerto")
PORT_NAME = "MK3 Screens"
LOG_PATH = DATA_DIR / "vdj_puerto.log"

_MIDI_DATA_CALLBACK = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), W.DWORD, ctypes.c_void_p)


class PortBridge:
    def __init__(self, sock):
        self._socket = sock
        self._lock = threading.Lock()
        self._last = {}  # campo -> último sysex
        self._buffer = None  # bytes del sysex en curso
        self.messages = 0
        dll = ctypes.WinDLL("teVirtualMIDI64.dll")
        dll.virtualMIDICreatePortEx2.restype = ctypes.c_void_p
        dll.virtualMIDICreatePortEx2.argtypes = [W.LPCWSTR, _MIDI_DATA_CALLBACK, ctypes.c_void_p, W.DWORD, W.DWORD]
        self._callback = _MIDI_DATA_CALLBACK(self._on_data)  # hay que guardar la referencia
        self._port = dll.virtualMIDICreatePortEx2(PORT_NAME, self._callback, None, 0x1FFFE, 0)
        if not self._port:
            raise RuntimeError(f"No se pudo crear el puerto virtual '{PORT_NAME}' (¿está instalado loopMIDI / teVirtualMIDI?)")

    def _on_data(self, port, data, length, instance):
        # Un error acá no puede cortar el programa (lo llama el driver)
        try:
            self._collect(data, length)
        except Exception as error:
            log.error("Error leyendo el puerto", exc_info=True)

    def _collect(self, data, length):
        if not data or not length:
            return
        for byte in bytes(data[:length]):
            if byte == 0xF0:
                self._buffer = bytearray()
            elif byte == 0xF7:
                if self._buffer is not None:
                    self._forward(bytes(self._buffer))
                self._buffer = None
            elif self._buffer is not None:
                self._buffer.append(byte)

    def _forward(self, message):
        if len(message) < 2 or message[0] != SYSEX_ID:
            return
        with self._lock:
            self._last[message[1]] = message
            self.messages += 1
        self._send(message)

    def _send(self, message):
        try:
            self._socket.sendto(message, ("127.0.0.1", DATA_PORT))
        except OSError:
            pass

    def send_all(self):
        with self._lock:
            messages = list(self._last.values())
        for message in messages:
            self._send(bytes([REPLAY_MARK]) + message)


def main():
    # Corre sin ventana (pythonw, ver dj_screens.start_vdj_port): todo va a vdj_puerto.log, con fecha y hora
    registro.configurar(archivo=LOG_PATH)
    stream = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = stream
    faulthandler.enable(stream)  # si se cae por algo de bajo nivel, queda el motivo en el registro
    atexit.register(lambda: log.info("vdj_puerto.py terminó"))
    log.info(f"Arrancó (pid {os.getpid()})")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(BRIDGE_ADDRESS)
    except OSError:
        log.info("Ya hay un vdj_puerto.py corriendo: este sale")
        return 0
    try:
        bridge = PortBridge(sock)
    except Exception:
        log.critical("No se pudo crear el puerto virtual", exc_info=True)
        return 1
    log.info(f"Puerto '{PORT_NAME}' creado; datos por UDP a {DATA_PORT}")
    # Un VirtualDJ abierto antes de esta hora no está conectado a este puerto (dj_screens.py avisa)
    PORT_STARTED_FILE.write_text(f"{time.time():.0f}", encoding="ascii")
    sock.settimeout(5.0)
    last_report = time.perf_counter()
    while True:
        try:
            request, _ = sock.recvfrom(64)
            if request == REQUEST_ALL:
                bridge.send_all()
        except (socket.timeout, ConnectionResetError):
            pass
        except OSError:
            log.error("UDP", exc_info=True)
            time.sleep(1.0)
        if time.perf_counter() - last_report > 60:
            log.info(f"{bridge.messages} mensajes de VirtualDJ recibidos en total")
            last_report = time.perf_counter()


if __name__ == "__main__":
    sys.exit(main())
