"""Contrato de controles de la Maschine MK3: cada control una sola vez, con quién reacciona en cada modo.

Es la fuente única de verdad de qué mensaje MIDI manda cada control (plantilla "CUSTOM MASCHINE" del Controller
Editor) y de qué programa se queda con él. Hoy los demás lugares (el script de Ableton, el XML de VirtualDJ, mode.py
de las pantallas) siguen escritos a mano: tools/validar_contrato.py los compara con este archivo y avisa si alguno
no coincide o si dos programas reaccionan al mismo control en el mismo modo sin que esté declarado acá.

Modos (los de la Maschine, no los de cada programa):
  ableton  modo Ableton, pads libres
  lock     modo Ableton con los pads fijados a VirtualDJ (LOCK apretado en modo DJ)
  dj       modo VirtualDJ (SAMPLING)
  reposo   SHIFT + CHANNEL: todo apagado hasta despertar

Dueños: quién reacciona al control en ese modo.
  ableton  solo el script de Ableton
  vdj      solo VirtualDJ
  ambos    los dos, a propósito: por_que dice para qué
  nadie    ninguno

"Reaccionar" es hacer algo que se oye o se ve (un parámetro, un deck, un clip, una vista). Que VirtualDJ solo anote
una variable ($encmode, $ps...) para no perder el hilo no cuenta: el validador lo lista aparte, porque es el
acoplamiento "de oído" que conviene ir sacando.

luz_compartida: VirtualDJ escribe la luz de ese control en un modo en que Ableton también la escribe. Solo vale si
está explicado.

Canales MIDI de 1 a 16 (VirtualDJ los numera de 0, mido también).
"""

from dataclasses import dataclass

MODOS = ("ableton", "lock", "dj", "reposo")
DUENOS = ("ableton", "vdj", "ambos", "nadie")


@dataclass(frozen=True)
class Control:
    nombre: str
    tipo: str  # "cc", "nota" o "pitch" (pitch bend: no tiene número)
    numero: int | None
    canal: int
    vdj: str | None  # nombre en VirtualDJ/Devices/MaschineMK3-VDJ.xml (None: VirtualDJ no lo define)
    ableton: str | None  # elemento de Ableton/CustomMaschineMK3/ControlElements.py; "pads[3]" = cuarto de la matriz
    ableton_modo: str = "ableton"
    lock: str = "ableton"
    dj: str = "vdj"
    reposo: str = "nadie"
    por_que: str = ""
    luz_compartida: str = ""

    def dueno(self, modo):
        return {"ableton": self.ableton_modo, "lock": self.lock, "dj": self.dj, "reposo": self.reposo}[modo]


_IGUAL = object()  # el nombre del contrato (vdj=None: VirtualDJ no lo define)


def _boton(nombre, cc, vdj=_IGUAL, ableton=None, **dueños):
    return Control(nombre, "cc", cc, 2, nombre if vdj is _IGUAL else vdj, ableton or nombre.lower().replace("_", ""),
                   **dueños)


_SALE_DE_DJ = "sale del modo DJ en los dos programas y en Ableton además elige su vista"
_DESPIERTA = "despierta a Ableton del reposo"

CONTROLES = (
    # Encoder grande
    _boton("ENCODER", 7, vdj="BROWSE", dj="ambos",
           por_que="en modo TEMPO gira el tempo de Ableton (VirtualDJ lo ignora en $encmode 3); si no, es de VirtualDJ"),
    _boton("ENCODER_PUSH", 8),
    _boton("ENCODER_TOUCH", 9, ableton="encodercap"),
    _boton("ENCODER_UP", 30),
    _boton("ENCODER_RIGHT", 31),
    _boton("ENCODER_DOWN", 32),
    _boton("ENCODER_LEFT", 33),

    # Botones de vista
    _boton("CHANNEL", 34, dj="ambos", reposo="ableton",
           por_que="SHIFT + CHANNEL pasa a reposo en los dos; CHANNEL solo " + _DESPIERTA),
    _boton("PLUGIN", 35, dj="ambos", reposo="ableton", por_que=_SALE_DE_DJ + "; en reposo " + _DESPIERTA),
    _boton("ARRANGER", 36, dj="ambos", reposo="ableton", por_que=_SALE_DE_DJ + "; en reposo " + _DESPIERTA),
    _boton("MIXER", 37, dj="ambos", reposo="ableton", por_que=_SALE_DE_DJ + "; en reposo " + _DESPIERTA),
    _boton("BROWSER", 38),
    _boton("SAMPLING", 39, ableton_modo="ambos", lock="ambos", dj="ambos", reposo="ambos",
           por_que="entra al modo DJ: Ableton deja de escuchar y VirtualDJ empieza (y prende el key lock)"),
    _boton("FILE", 40),
    _boton("SETTING", 41),
    _boton("AUTO", 42),
    _boton("MACRO", 43, dj="ableton", por_que="SHIFT + MACRO reinicia las pantallas desde cualquier modo"),

    # Modo del encoder y modificadores
    _boton("VOLUME", 44, dj="ambos", por_que="los dos llevan el modo del encoder (VOLUME / SWING / TEMPO)"),
    _boton("SWING", 45, dj="ambos", por_que="los dos llevan el modo del encoder (VOLUME / SWING / TEMPO)"),
    _boton("NOTEREP", 46),
    _boton("TEMPO", 47, dj="ambos",
           por_que="los dos llevan el modo del encoder; SHIFT + TEMPO iguala el tempo de Ableton con VirtualDJ"),
    _boton("LOCK", 48, lock="ambos", dj="ambos",
           por_que="en modo DJ fija los pads a VirtualDJ; en Ableton los suelta: los dos llevan el estado"),
    _boton("PITCH", 49),
    _boton("MOD", 50),
    _boton("PERFORM", 51),
    _boton("NOTES", 52),
    _boton("RESTART", 53),
    _boton("ERASE", 54),
    _boton("TAP", 55, dj="ableton"),
    _boton("FOLLOW", 56),
    _boton("PLAY", 57, dj="ableton"),
    _boton("REC", 58),
    _boton("STOP", 59, dj="ableton"),
    _boton("PEDAL_TIP", 64, vdj=None, ableton="pedaltip", dj="nadie"),
    _boton("PEDAL_RING", 65, vdj=None, ableton="pedalring", dj="nadie"),

    # Páginas de pads: con LOCK son de VirtualDJ
    _boton("FIXEDVEL", 80),
    _boton("PADMODE", 81, lock="vdj"),
    _boton("KEYBOARD", 82, lock="vdj"),
    _boton("CHORDS", 83, lock="vdj"),
    _boton("STEP", 84, lock="vdj"),
    _boton("SCENE", 85),
    _boton("PATTERN", 86),
    _boton("EVENTS", 87),
    _boton("VARIATION", 88),
    _boton("DUPLICATE", 89),
    _boton("SELECT", 90),
    _boton("SOLO", 91),
    _boton("MUTE", 92),

    # Grupos A-H: con LOCK son de VirtualDJ (efectos y preescucha)
    *(_boton(f"GROUP_{letra}", 100 + indice, ableton=f"group_buttons[{indice}]", lock="vdj")
      for indice, letra in enumerate("ABCDEFGH")),

    _boton("LEFT", 110),
    _boton("RIGHT", 111),
    # VirtualDJ lee SHIFT por sysex (SHIFT_ON / SHIFT_OFF); el CC 119 solo lo define Ableton
    _boton("SHIFT", 119, vdj=None, dj="ambos",
           por_que="modificador en los dos programas: Ableton lo sigue también en modo DJ (SHIFT + STOP, TEMPO, MACRO)"),

    # Tocar las perillas (canal 2) y las perillas (V-Pots MCU, canal 1)
    *(_boton(f"KNOB{n}_TOUCH", 9 + n, ableton=f"knob_touch_buttons[{n - 1}]") for n in range(1, 9)),
    *(Control(f"KNOB{n}", "cc", 15 + n, 1, f"KNOB{n}", f"knobs[{n - 1}]") for n in range(1, 9)),

    # Botones 1-8 sobre las pantallas (notas, canal 2). 1-4 son de VirtualDJ en todos los modos (stems)
    *(Control(f"BTN{n}", "nota", n - 1, 2, f"BTN{n}", f"track_buttons[{n - 1}]",
              ableton_modo="vdj", lock="vdj", dj="vdj", reposo="vdj") for n in range(1, 5)),
    *(Control(f"BTN{n}", "nota", n - 1, 2, f"BTN{n}", f"track_buttons[{n - 1}]") for n in range(5, 9)),

    # Pads (notas 60-75, canal 1): con LOCK son de VirtualDJ
    *(Control(f"PAD{n}", "nota", 59 + n, 1, f"PAD{n}", f"pads[{n - 1}]", lock="vdj") for n in range(1, 17)),

    # Tira táctil: movimiento (pitch bend canal 1) y soltar (pitch bend canal 2). Con LOCK es el crossfader
    Control("TOUCHSTRIP", "pitch", None, 1, "TOUCHSTRIP", "touchstrip", lock="vdj",
            luz_compartida="en modo Ableton (PITCH) VirtualDJ prende las luces según el dedo, porque si el script "
                           "recibiera el pitch bend Ableton no se lo pasaría a la pista; el script solo la centra"),
    Control("TOUCHSTRIP_RELEASE", "pitch", None, 2, "TOUCHSTRIP_RELEASE", "touchstripcap", lock="vdj"),
)

# La pantalla (texto MCU de 4 x 28) no es un control, pero también tiene dos escritores
PANTALLA_COMPARTIDA = ("al salir del modo DJ VirtualDJ manda una línea vacía para forzar el redibujado, y Ableton "
                       "redibuja enseguida (VDJ_REFRESH_DELAY); las pantallas gráficas no dependen de este texto")

POR_NOMBRE = {control.nombre: control for control in CONTROLES}
