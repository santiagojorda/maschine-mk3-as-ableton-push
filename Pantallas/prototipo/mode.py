"""Sigue el modo de la Maschine (DJ o Ableton) escuchando su puerto MIDI.

Usa los mismos botones que el mapeo de maschine-mk3-ableton-virtualdj
(Control Change en canal MIDI 2, valor 127 al apretar):
SAMPLING = CC 39 entra a modo DJ; MIXER = CC 37 y PLUGIN = CC 35 vuelven a Ableton.

El puerto se abre como un cliente más: Windows MIDI Services deja que varios
programas lo usen a la vez.
"""

import threading
import time

import logging

import mido

log = logging.getLogger("midi")

DJ = "dj"
ABLETON = "ableton"

MODE_CHANNEL = 1  # mido numera desde 0: 1 = canal MIDI 2
SAMPLING_CC = 39
MIXER_CC = 37
PLUGIN_CC = 35
ARRANGER_CC = 36  # Entra a vista Session y vuelve a Ableton
BUTTON_NAMES = {SAMPLING_CC: "SAMPLING", MIXER_CC: "MIXER", PLUGIN_CC: "PLUGIN", ARRANGER_CC: "ARRANGER"}
BROWSER_CC = 38
# En modo DJ, tocar algo de la mezcla cierra el browser y vuelve a la vista normal (canal 2):
KNOB_TOUCH_CCS = range(10, 18)  # tocar una perilla (jogs, tempo, volumen, filtro)
PAD_PAGE_CCS = range(81, 85)  # KEYBOARD, PAD MODE, CHORDS, STEP
GROUP_CCS = range(100, 108)  # A-H: efectos y preescucha

DEFAULT_PORT_HINT = "Maschine MK3 Ctrl MIDI"


def find_input_port(hint):
    names = mido.get_input_names()
    for name in names:
        if hint.lower() in name.lower():
            return name
    raise RuntimeError(f"No hay un puerto MIDI que contenga '{hint}'. Puertos: {names}")


def mode_for_message(message):
    """Devuelve DJ, ABLETON o None si el mensaje no cambia el modo."""
    if message.type != "control_change" or message.channel != MODE_CHANNEL or message.value == 0:
        return None
    if message.control == SAMPLING_CC:
        return DJ
    if message.control in (MIXER_CC, PLUGIN_CC, ARRANGER_CC):
        return ABLETON
    return None


def is_browser_press(message):
    return (message.type == "control_change" and message.channel == MODE_CHANNEL
            and message.control == BROWSER_CC and message.value > 0)


def closes_browser(message):
    if message.type == "pitchwheel":  # la tira táctil = crossfader
        return True
    return (message.type == "control_change" and message.channel == MODE_CHANNEL and message.value > 0
            and (message.control in KNOB_TOUCH_CCS or message.control in PAD_PAGE_CCS
                 or message.control in GROUP_CCS))


class ModeWatcher:
    def __init__(self, port_hint=DEFAULT_PORT_HINT, start_mode=ABLETON, on_change=None, on_message=None):
        self._lock = threading.Lock()
        self._mode = start_mode
        self.last_button_time = 0.0  # perf_counter del último SAMPLING / MIXER / PLUGIN
        self.browser = False  # en modo DJ, BROWSER prende y apaga la vista de carpetas y temas
        self._on_change = on_change
        self._on_message = on_message
        self._port_hint = port_hint
        self._port = None
        self.port_name = None
        self._last_check = 0.0
        self.ensure_connected(force=True)

    def ensure_connected(self, force=False, every_seconds=3.0):
        """Si la Maschine se apagó o se desenchufó, su puerto MIDI desaparece (y al volver puede tener otro
        nombre, "... MIDI 2"): se vuelve a buscar y abrir. Devuelve True si el puerto está abierto."""
        now = time.perf_counter()
        if not force and now - self._last_check < every_seconds:
            return self._port is not None
        self._last_check = now
        try:
            names = mido.get_input_names()
        except Exception:
            return self._port is not None
        if self._port is not None and self.port_name in names:
            return True
        if self._port is not None:
            log.warning(f"Se perdió el puerto MIDI '{self.port_name}'; espero que vuelva la Maschine")
            try:
                self._port.close()
            except Exception:
                pass
            self._port = None
            self.port_name = None
        candidates = [name for name in names if self._port_hint.lower() in name.lower()]
        if not candidates:
            return False
        try:
            self._port = mido.open_input(candidates[0], callback=self._handle)
            self.port_name = candidates[0]
            log.info(f"Puerto MIDI abierto: '{self.port_name}'")
            return True
        except Exception as error:
            log.error(f"No se pudo abrir '{candidates[0]}': {error}", exc_info=True)
            return False

    @property
    def mode(self):
        with self._lock:
            return self._mode

    def _handle(self, message):
        if self._on_message:
            self._on_message(message)
        if is_browser_press(message):
            with self._lock:
                self.browser = not self.browser
                browser = self.browser
            log.info(f"Botón BROWSER: browser {'abierto' if browser else 'cerrado'}")
            return
        if self.browser and closes_browser(message):
            with self._lock:
                self.browser = False
            log.info(f"Se cierra el browser: {message}")
            return
        new_mode = mode_for_message(message)
        if new_mode is None:
            return
        log.info(f"Botón de modo: {BUTTON_NAMES.get(message.control, message.control)} -> {new_mode}")
        with self._lock:
            changed = new_mode != self._mode
            self._mode = new_mode
            self.browser = False
            self.last_button_time = time.perf_counter()
        if changed and self._on_change:
            self._on_change(new_mode)

    def sync(self, reported_mode, quiet_seconds=1.0):
        """Toma el modo que informa el script de Ableton (al arrancar, o si se desincronizaron),
        salvo justo después de un botón: el script puede tardar un instante en enterarse."""
        with self._lock:
            if (reported_mode is None or reported_mode == self._mode
                    or time.perf_counter() - self.last_button_time < quiet_seconds):
                return False
            self._mode = reported_mode
        if self._on_change:
            self._on_change(reported_mode)
        return True

    def close(self):
        if self._port is not None:
            self._port.close()
