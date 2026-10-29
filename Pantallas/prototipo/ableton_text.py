"""Recibe el texto de pantalla que manda el script de Ableton y lo dibuja.

El script CustomMaschineMK3 (Config.SCREEN_BRIDGE_PORT) manda por UDP a
127.0.0.1 una copia de cada línea MCU que le escribe a la Maschine:
F0 00 00 66 17 12 <posición> <caracteres...> F7, con posición = línea x 28.

Son 4 líneas de 28 caracteres: las líneas 0 y 2 van en la pantalla izquierda,
la 1 y la 3 en la derecha (arriba y abajo). La línea de abajo trae los valores
de las 4 perillas de esa pantalla, separados por "|".

Por el mismo puerto llega, 10 veces por segundo, un estado en JSON (empieza
con "{"): la vista, las 8 perillas con su parámetro y, en el mixer, el color y
el nivel de cada track. ableton_ui.py lo dibuja con faders y knobs.
"""

import json
import logging
import socket
import threading
import time

from PIL import Image, ImageDraw, ImageFont

from maschine_display import HEIGHT, WIDTH

log = logging.getLogger("ableton")

MCU_DISPLAY_HEADER = bytes((0xF0, 0x00, 0x00, 0x66, 0x17, 0x12))
LINES = 4
LINE_LENGTH = 28
DEFAULT_PORT = 9017

# Líneas (arriba, abajo) de cada pantalla
SCREEN_LINES = ((0, 2), (1, 3))

TOP_COLOR = (255, 255, 255)
BOTTOM_COLOR = (90, 200, 255)
DIVIDER_COLOR = (60, 60, 60)
MARGIN = 6


class AbletonText:
    """Escucha el puerto UDP en un hilo propio y guarda las 4 líneas."""

    def __init__(self, port=DEFAULT_PORT):
        self._lock = threading.Lock()
        self._chars = [" "] * (LINES * LINE_LENGTH)
        self._received = False
        self._state = None
        self._state_time = 0.0
        self.state_version = 0
        self._reported = (None, 0.0)
        self._tempo = (None, 0.0)  # tempo de Ableton que manda el script en modo DJ
        self._flash = (None, 0.0)  # (BPM, hasta cuándo) de la vista de tempo pasajera de SHIFT + TEMPO
        self.flash_version = 0
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(("127.0.0.1", port))
        self._socket.settimeout(0.5)
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self):
        while self._running:
            try:
                # El estado JSON pesa más de 1 KB: con un búfer chico Windows descarta el paquete (WSAEMSGSIZE)
                data = self._socket.recv(65535)
            except socket.timeout:
                continue
            except OSError as error:  # en Windows un UDP puede devolver ConnectionResetError: se ignora
                if not self._running:
                    return
                if getattr(error, "winerror", None) != 10054:
                    log.warning(f"UDP de Ableton: {error}")
                continue
            self._apply(data)

    def _apply(self, data):
        if data[:1] == b"{":
            try:
                state = json.loads(data)
            except ValueError:
                return
            with self._lock:
                now = time.perf_counter()
                if state.get("type") == "tempo_flash":
                    # SHIFT + TEMPO igualó el tempo: la vista de tempo se ve unos segundos, en cualquier vista
                    self._flash = (state.get("bpm"), now + float(state.get("seconds", 3.0)))
                    self.flash_version += 1
                    return
                if state.get("type") == "tempo":
                    # En modo DJ, con el encoder en TEMPO: el tempo de Live para la vista de tempo
                    self._tempo = (state.get("bpm"), now)
                    return
                if state.get("type") == "mode":
                    # En modo VirtualDJ el script solo avisa el modo
                    self._reported = ("dj" if state.get("vdj") else "ableton", now)
                    return
                self._reported = ("ableton", now)
                self._state = state
                self._state_time = now
                self.state_version += 1
            return
        if not data.startswith(MCU_DISPLAY_HEADER) or len(data) < 8:
            return
        position = data[6]
        text = data[7:-1] if data.endswith(b"\xF7") else data[7:]
        with self._lock:
            for offset, code in enumerate(text):
                index = position + offset
                if index >= len(self._chars):
                    break
                self._chars[index] = chr(code) if 32 <= code < 127 else " "
            self._received = True

    @property
    def received(self):
        with self._lock:
            return self._received

    def reported_mode(self, max_age=1.0):
        """El modo en que está el script de Ableton ("dj" o "ableton"), o None si no avisó hace poco."""
        with self._lock:
            mode, when = self._reported
            return mode if mode and time.perf_counter() - when <= max_age else None

    def tempo(self, max_age=1.0):
        """El tempo de Ableton (BPM) que mandó el script en modo DJ, o None si no llegó o es viejo."""
        with self._lock:
            bpm, when = self._tempo
            return bpm if bpm and time.perf_counter() - when <= max_age else None

    def tempo_flash(self):
        """El tempo (BPM) de la vista de tempo pasajera, o None si no hay una activa."""
        with self._lock:
            bpm, until = self._flash
            return bpm if bpm and time.perf_counter() < until else None

    def state(self, max_age=1.0):
        """El último estado JSON, o None si no llegó o es viejo (el script dejó de mandarlo)."""
        with self._lock:
            if self._state is None or time.perf_counter() - self._state_time > max_age:
                return None
            return self._state

    def last_state(self):
        """El último estado JSON que llegó, por viejo que sea (o None si nunca llegó)."""
        with self._lock:
            return self._state

    def lines(self):
        with self._lock:
            text = "".join(self._chars)
        return [text[line * LINE_LENGTH:(line + 1) * LINE_LENGTH] for line in range(LINES)]

    def screen_lines(self, display):
        """(arriba, abajo) de una pantalla."""
        lines = self.lines()
        top, bottom = SCREEN_LINES[display]
        return lines[top], lines[bottom]

    def close(self):
        self._running = False
        self._socket.close()


def _load_font(bold):
    names = ("consolab.ttf", "consola.ttf") if bold else ("consola.ttf",)
    for name in names:
        try:
            font = ImageFont.truetype(name, 40)
        except OSError:
            continue
        # Achicar hasta que entren 28 caracteres en el ancho de la pantalla
        size = 40
        while size > 10 and font.getlength("M" * LINE_LENGTH) > WIDTH - 2 * MARGIN:
            size -= 1
            font = ImageFont.truetype(name, size)
        return font
    return ImageFont.load_default()


_TOP_FONT = None
_BOTTOM_FONT = None


def render_screen(top, bottom):
    """Dibuja una pantalla: la línea de arriba en blanco y la de abajo (perillas) abajo, en celeste."""
    global _TOP_FONT, _BOTTOM_FONT
    if _TOP_FONT is None:
        _TOP_FONT = _load_font(bold=True)
        _BOTTOM_FONT = _load_font(bold=False)

    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    draw.text((MARGIN, 24), top.rstrip(), fill=TOP_COLOR, font=_TOP_FONT)

    bottom_top = HEIGHT - 70
    draw.line((MARGIN, bottom_top - 14, WIDTH - MARGIN, bottom_top - 14), fill=DIVIDER_COLOR, width=1)
    draw.text((MARGIN, bottom_top), bottom.rstrip(), fill=BOTTOM_COLOR, font=_BOTTOM_FONT)
    return image
