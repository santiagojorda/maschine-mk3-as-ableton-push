"""
Arma la definicion y el mapeo de VirtualDJ de la Maschine (Devices/ y Mappers/) desde sus fuentes:

  fuente/dispositivo.xml   la definicion, sin las luces de los pads y de los botones 1-4
  fuente/mapeo.vdj         las acciones escritas a mano, legibles (ver su cabecera)
  este archivo             los pads, los botones 1-4, sus luces, el modo info de SELECT y los carteles de stems

Los dos XML de Devices/ y Mappers/ no se editan: se editan las fuentes y se corre  python generar.py
(python generar.py --revisar dice si los XML estan al dia, sin escribir; los tests lo revisan solos).
Despues: python tools/instalar.py los copia a %LocalAppData%\\VirtualDJ, y hay que reiniciar VirtualDJ.

Los pads responden con $pads = 1 (modo VirtualDJ, o pads fijados a VirtualDJ con LOCK).
Las paginas se eligen con KEYBOARD (0, hot cues), PAD MODE (1, transporte), CHORDS (2, stems) y STEP (3, todo apagado).
Columnas 1-2 = deck 1, columnas 3-4 = deck 2. Las filas se cuentan desde abajo (fila 0 = abajo).

Modo info: mientras se mantiene SELECT (en modo VirtualDJ), tocar un pad o un boton de HELP_BUTTONS no hace su accion:
guarda su codigo en $help y la pantalla izquierda muestra su nombre (linea de abajo vacia).
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
DEVICE = os.path.join(HERE, "Devices", "MaschineMK3-VDJ.xml")
MAPPER = os.path.join(HERE, "Mappers", "MASCHINEMK3VDJ - Mapeo Personalizado.xml")
SOURCE_DEVICE = os.path.join(HERE, "fuente", "dispositivo.xml")
SOURCE_MAPPER = os.path.join(HERE, "fuente", "mapeo.vdj")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import vdjscript  # noqa: E402


def read_source_mapper():
    """fuente/mapeo.vdj -> el texto del mapeo sin lo que genera este archivo (las acciones, en una linea)."""
    lines, name, action = [], None, []

    def close():
        if name is not None:
            text = escape(vdjscript.compactar(" ".join(action)), {'"': "&quot;"})
            lines.append(f'\t<map value="{name}" action="{text}" />')

    for line in open(SOURCE_MAPPER, encoding="utf-8").read().split("\n"):
        if name is not None and line.startswith("    "):
            action.append(line)
            continue
        close()
        name, action = None, []
        if line.startswith("| ") or line == "|":
            lines.append(line[2:])
        elif line.startswith("#") or not line.strip():
            continue
        else:
            found = re.fullmatch(r"([A-Z0-9_]+) =(.*)", line)
            if not found:
                raise SystemExit(f"fuente/mapeo.vdj: no entiendo la linea {line!r}")
            name, action = found[1], [found[2]]
    close()
    return "\n".join(lines) + "\n"

# MK3 color index = 4 * color + brightness
RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, VIOLET, WHITE = 1, 2, 5, 7, 9, 11, 13, 31
DIM, BRIGHT = 0, 3


def color(base, level):
    return 4 * base + level


DECK_COLUMNS = {1: (0, 1), 2: (2, 3)}
DECK_CUE_COLOR = {1: color(BLUE, BRIGHT), 2: color(ORANGE, BRIGHT)}

# (fila desde abajo, columna dentro del deck, accion, condicion activa, condicion inactiva, color, nombre)
# Sin condiciones = color tenue fijo. El nombre se muestra en el modo info (sin deck: el mismo para los dos lados)
# Sincronizados = mismo BPM (match_bpm, queda fijo) o is_sync. is_sync solo no alcanza: mientras suena exige
# tambien la fase, y si se corre un poco se apaga y prende. Fuerte en los dos pads SYNC a la vez.
SYNCED = ("DECK match_bpm ? true : (deck 1 match_bpm ? true : (deck 2 match_bpm ? true : "
          "(deck 1 is_sync ? true : (deck 2 is_sync ? true : false))))")

TRANSPORT = [
    (0, 0, "play", "play", "play ? false : true", GREEN, "PLAY"),
    (0, 1, "pause", "play ? false : true", "play", RED, "PAUSA"),
    (1, 0, None, None, None, None, None),
    # Luz: fuerte en los dos pads SYNC cuando los decks estan sincronizados (SYNCED).
    # No usar la consulta "sync": titila con el ritmo aunque el deck no este sincronizado.
    (1, 1, "sync", f"({SYNCED})", f"({SYNCED}) ? false : true", YELLOW, "SYNC"),  # arriba de PAUSA (INICIO se saco)
    # LOOP prende y apaga el loop con el largo que tenga (1/2, x2 lo cambian); "loop 4" lo volvia siempre a 4
    (2, 0, "loop", "loop", "loop ? false : true", VIOLET, "LOOP"),
    # PITCH LOCK = el candado de VirtualDJ (pitch_lock). El key lock (no cambia el tono) queda siempre activo:
    # se activa al entrar a SAMPLING y en cada cambio de tempo con las perillas 3-4
    (2, 1, "pitch_lock", "pitch_lock", "pitch_lock ? false : true", ORANGE, "PITCH LOCK"),
    (3, 0, "loop_half", None, None, CYAN, "LOOP 1/2"),
    (3, 1, "loop_double", None, None, CYAN, "LOOP X2"),
]

STEM_NAMES = ["Vocal", "Instru", "Bass", "Kick", "HiHat"]


# Stems (pedido del usuario): cada pad es independiente y puede haber varios prendidos.
#   RESET        prende todo                                   | fuerte: suenan todos los stems
#   INSTRUMENTAL alterna Instru y Bass juntos: si suenan los   | fuerte: suenan Instru y Bass
#                dos los apaga, si no los prende               |
#   VOZ          alterna solo la voz                           | fuerte: suena la voz
#   KICK         alterna solo el kick                          | fuerte: suena el kick
#   HATS         alterna solo el hihat (a la izq. de KICK)   | fuerte: suena el hihat
# Despues de RESET quedan prendidos todos. DECK se reemplaza por "deck n".
# Se usa stem_pad, igual que la pagina de stems propia de VirtualDJ: como consulta es true mientras el stem
# suena, y como accion alterna el mute. (mute_stem como consulta no queda claro y DRUMLESS terminaba sacando la voz.)
# El estado de cada stem lo guarda el mapeo en '$muteN_<stem>' (1 = silenciado), en vez de preguntarle a
# VirtualDJ con stem_pad: como consulta no queda claro qué devuelve, y los toggles (INSTRUMENTAL, botones 1-4)
# no volvían. #N se reemplaza por el número de deck. RESET pone todo en 0.
def muted_var(name):
    return f"'$mute#N_{name.lower()}'"


def playing(name):
    return f"var {muted_var(name)} 0"


# Las acciones fijan el estado con mute_stem on / off. stem_pad como accion en un pad es un toggle temporal
# si se mantiene apretado, y dos stem_pad en la misma accion (INSTRUMENTAL) VirtualDJ los toma como dos pads
# juntos: INSTRUMENTAL no volvia. Las consultas siguen con stem_pad.
def set_mute(name, muted):
    return f"(DECK mute_stem '{name.lower()}' {'on' if muted else 'off'} & set {muted_var(name)} {1 if muted else 0})"


def toggle(name):  # VOZ, KICK, HATS: si suena lo silencia, si no lo prende
    return f"({playing(name)} ? {set_mute(name, True)} : {set_mute(name, False)})"


def all_playing(names):
    condition = "true"
    for n in reversed(names):
        condition = f"{playing(n)} ? ({condition}) : false"
    return condition


def all_muted(names):
    condition = "true"
    for n in reversed(names):
        condition = f"{playing(n)} ? false : ({condition})"
    return condition


def exact_state(muted):  # true cuando estan silenciados exactamente esos stems
    condition = "true"
    for n in reversed(STEM_NAMES):
        condition = (f"{playing(n)} ? false : ({condition})" if n in muted
                     else f"{playing(n)} ? ({condition}) : false")
    return condition


def stems_apply(muted):
    return " & ".join(set_mute(n, n in muted) for n in STEM_NAMES)


def stems_pad(row, action, state, color, name):
    return (row, 1, action, f"({state})", f"({state}) ? false : true", color, name)


ALL_ON = all_playing(STEM_NAMES)
INSTRUMENTS_ON = all_playing(["Instru", "Bass"])
INSTRUMENTAL = (f"(({INSTRUMENTS_ON}) ? ({set_mute('Instru', True)} & {set_mute('Bass', True)}) : "
                f"({set_mute('Instru', False)} & {set_mute('Bass', False)}))")

# Botones 1-4 (DRUMLESS / BATERIA): toggles puros (pedido del usuario). stem_pad como accion, con un toque
# largo, funciona mientras se mantiene y vuelve atras al soltar ("long press will work as temporary toggle"),
# asi que aca se fija el estado con mute_stem on / off. Las consultas siguen con stem_pad.
def force_mute(name, muted):
    return set_mute(name, muted)


def force_apply(muted):
    return " & ".join(force_mute(n, n in muted) for n in STEM_NAMES)


DRUMLESS_STATE = all_muted(["Kick", "HiHat"])
DRUMLESS = (f"(({DRUMLESS_STATE}) ? ({force_mute('Kick', False)} & {force_mute('HiHat', False)}) : "
            f"({force_mute('Kick', True)} & {force_mute('HiHat', True)}))")
BATERIA_STATE = exact_state(("Vocal", "Instru", "Bass"))
BATERIA = f"(({BATERIA_STATE}) ? ({force_apply(())}) : ({force_apply(('Vocal', 'Instru', 'Bass'))}))"
# nombre -> (accion, estado activo, codigo en $stemN para la pantalla)
BUTTON_MODES = {"DRUMLESS": (DRUMLESS, DRUMLESS_STATE, 21), "BATERIA": (BATERIA, BATERIA_STATE, 22)}

STEMS = [
    # columna derecha de cada deck, de arriba hacia abajo: RESET, INSTRUMENTAL, VOZ, KICK
    stems_pad(3, stems_apply(()), ALL_ON, YELLOW, "RESET STEMS"),
    stems_pad(2, INSTRUMENTAL, INSTRUMENTS_ON, BLUE, "INSTRUMENTAL"),
    stems_pad(1, toggle("Vocal"), playing("Vocal"), GREEN, "VOZ"),
    stems_pad(0, toggle("Kick"), playing("Kick"), RED, "KICK"),
    # columna izquierda: vacia (apagada)
    (3, 0, None, None, None, None, None),
    (2, 0, None, None, None, None, None),
    (1, 0, None, None, None, None, None),
    (0, 0, toggle("HiHat"), f"({playing('HiHat')})", f"({playing('HiHat')}) ? false : true", ORANGE, "HATS"),  # a la izquierda de KICK
]

# Botones con nombre en el modo info: control -> (nombre, es slider). Los sliders se leen con param_bigger 0.5.
# SAMPLING / MIXER / PLUGIN no van: Ableton tambien los escucha y cambiaria de modo igual.
HELP_BUTTONS = {
    "BTN1": ("DRUMLESS", True), "BTN2": ("BATERIA", True), "BTN3": ("DRUMLESS", True), "BTN4": ("BATERIA", True),
    "GROUP_A": ("REVERB", False), "GROUP_B": ("REVERB", False),
    "GROUP_C": ("FLANGER", False), "GROUP_D": ("FLANGER", False),
    "GROUP_E": ("ECHO", False), "GROUP_F": ("ECHO", False),
    "GROUP_G": ("PREESCUCHA", False), "GROUP_H": ("PREESCUCHA", False),
    "RESTART": ("+PERILLA / +ERASE=RESET", True), "LEFT": ("ELEGIR DECK 1", False),
    "RIGHT": ("ELEGIR DECK 2", False), "FOLLOW": ("ABLETON LINK", False),
    "ENCODER_PUSH": ("CARPETAS / TEMAS", False), "ENCODER_UP": ("SUBIR EN LA LISTA", False),
    "ENCODER_DOWN": ("BAJAR EN LA LISTA", False), "ENCODER_LEFT": ("CARGAR / ABRIR CARPETA", False),
    "ENCODER_RIGHT": ("CARGAR / ABRIR CARPETA", False),
    "VOLUME": ("VOLUMEN MASTER (ENCODER)", False), "SWING": ("VOLUMEN AURIS (ENCODER)", False), "LOCK": ("FIJAR PADS EN VDJ", False),
    "KEYBOARD": ("PAGINA HOT CUES", False), "PADMODE": ("PAGINA TRANSPORTE", False),
    "CHORDS": ("PAGINA STEMS", False), "STEP": ("PAGINA PADS APAGADOS", False),
    "ERASE": ("BORRAR (+RESTART=RESET)", True), "NOTES": ("PREESCUCHA (MANTENER)", True),
}
# Botones 1-4 sobre la pantalla (MAICOL, SESSION, EN, TU): 1 y 3 = DRUMLESS (saca kick y hihat) del deck 1 / 2,
# 2 y 4 = BATERIA (deja solo kick y hihat). Volver a tocarlo deshace (DRUMLESS devuelve kick y hihat, BATERIA prende todo).
# Luz prendida = el modo esta activo. Son solo de VirtualDJ y andan en los dos modos (el script de Ableton los ignora siempre).
STEM_BUTTONS = {"BTN1": (1, "DRUMLESS"), "BTN2": (1, "BATERIA"), "BTN3": (2, "DRUMLESS"), "BTN4": (2, "BATERIA")}
HELP_IDLE = "INFO: TOCA UN CONTROL"
STEM_DISPLAY_TIME = "1500ms"  # cuanto se ve el nombre / estado del stem tocado
# LOOP 1/2 y LOOP X2 (pads 13-16 de PAD MODE) muestran el largo del loop en la pantalla del deck, con la misma capa
# y el mismo tiempo que los stems ($stemN = LOOP_DISPLAY_CODE). get_loop = largo en tiempos (beats)
LOOP_DISPLAY_NAMES = ("LOOP 1/2", "LOOP X2")
LOOP_DISPLAY_CODE = 20


def pad_number(row, column):
    return row * 4 + column + 1


def build_pads():
    pads = {}
    for deck, (c0, c1) in DECK_COLUMNS.items():
        cue = 1
        for row in (3, 2, 1, 0):  # cues 1-8 de arriba hacia abajo, izquierda a derecha
            for column in (c0, c1):
                pads.setdefault(pad_number(row, column), {})["cue"] = (deck, cue)
                cue += 1
        for page, layout in (("transport", TRANSPORT), ("stems", STEMS)):
            for row, column, action, on, off, base, name in layout:
                pads[pad_number(row, (c0, c1)[column])][page] = (deck, action, on, off, base, name)
    return pads


def deck_action(deck, action):
    if "DECK" in action or "#N" in action:
        return action.replace("DECK", f"deck {deck}").replace("#N", str(deck)).replace(" & ", " &amp; ")
    return " &amp; ".join(f"deck {deck} {part}" for part in action.split(" & "))


def deck_condition(deck, condition):
    if "DECK" in condition or "#N" in condition:
        return condition.replace("DECK", f"deck {deck}").replace("#N", str(deck))
    return f"deck {deck} {condition}"


def add_states(states, page, entry):
    deck, action, on, off, base, _ = entry
    if action is None:
        states.setdefault(0, {})[page] = "true"
    elif on is None:
        states.setdefault(color(base, DIM), {})[page] = "true"
    else:
        states.setdefault(color(base, BRIGHT), {})[page] = deck_condition(deck, on)
        states.setdefault(color(base, DIM), {})[page] = deck_condition(deck, off)


def matching_paren(text, start):
    """Index of the parenthesis closing the one at text[start]."""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("parentesis sin cerrar")


SELECT_PREFIX = "var '$select' 1 ? ("


def strip_select(action):
    """Remove a previous info-mode wrapper: var '$select' 1 ? (X) : (ORIGINAL) -> ORIGINAL."""
    if not action.startswith(SELECT_PREFIX):
        return action
    first_close = matching_paren(action, len(SELECT_PREFIX) - 1)
    rest = action[first_close + 1:]
    assert rest.startswith(" : (") and rest.endswith(")"), action
    return rest[len(" : ("):-1]


def generate(device, mapper):
    """A la definicion y al mapeo de las fuentes les agrega lo que se genera; devuelve los dos XML y un resumen."""
    help_texts = {}  # code -> text

    def help_code(text):
        for code, known in help_texts.items():
            if known == text:
                return code
        code = len(help_texts) + 1
        help_texts[code] = text
        return code
    device_lines, led_lines, pad_lines = [], [], []
    for pad, entries in sorted(build_pads().items()):
        note = 0x3B + pad
        deck, cue = entries["cue"]
        transport, stems = entries["transport"], entries["stems"]
        states = {}
        states.setdefault(DECK_CUE_COLOR[deck], {})[0] = f"deck {deck} hot_cue {cue}"
        states.setdefault(0, {})[0] = f"deck {deck} hot_cue {cue} ? false : true"
        add_states(states, 1, transport)
        add_states(states, 2, stems)
        states.setdefault(0, {})[3] = "true"
        for value, pages in sorted(states.items()):
            name = f"LED_P{pad}_{value:02X}"
            device_lines.append(f'  <sysex value="90{note:02X}{value:02X}" name="{name}" />')
            expression = "false"
            for page, condition in pages.items():
                expression = f"var '$padpage' {page} ? ({condition}) : ({expression})"
            led_lines.append(f"\t<map value=\"{name}\" action=\"var '$pads' ? ({expression}) : false\" />")

        # info mode: one code per distinct name (shared by both decks)
        page_names = [f"CUE {cue}",
                      transport[5] if transport[1] else "SIN FUNCION",
                      stems[5] if stems[1] else "SIN FUNCION",
                      "PADS APAGADOS"]
        codes = [help_code(text) for text in page_names]
        set_help = (f"var '$padpage' 0 ? set '$help' {codes[0]} : (var '$padpage' 1 ? set '$help' {codes[1]} : "
                    f"(var '$padpage' 2 ? set '$help' {codes[2]} : set '$help' {codes[3]}))")

        cue_action = f"var '$erase' ? deck {deck} delete_cue {cue} : deck {deck} hot_cue {cue}"
        transport_action = f"deck {transport[0]} {transport[1]}" if transport[1] else "nothing"
        if transport[5] in LOOP_DISPLAY_NAMES:
            timer = f"stem{transport[0]}"
            transport_action += (f" &amp; set '$stem{transport[0]}' {LOOP_DISPLAY_CODE} &amp; repeat_stop '{timer}' &amp; "
                                 f"repeat_start '{timer}' {STEM_DISPLAY_TIME} 1 &amp; set '$stem{transport[0]}' 0")
        stems_action = deck_action(stems[0], stems[1]) if stems[1] else "nothing"
        if stems[1]:
            code = [entry[6] for entry in STEMS].index(stems[5]) + 1
            timer = f"stem{stems[0]}"
            stems_action += (f" &amp; set '$stem{stems[0]}' {code} &amp; repeat_stop '{timer}' &amp; "
                             f"repeat_start '{timer}' {STEM_DISPLAY_TIME} 1 &amp; set '$stem{stems[0]}' 0")
        pad_lines.append(
            f"\t<map value=\"PAD{pad}\" action=\"var '$pads' ? ({SELECT_PREFIX}{set_help}) : "
            f"(var '$padpage' 3 ? nothing : "
            f"(var '$padpage' 2 ? ({stems_action}) : "
            f"(var '$padpage' 1 ? ({transport_action}) : ({cue_action}))))) : nothing\" />")

    for control, (deck, name) in STEM_BUTTONS.items():
        mode_action, mode_state, code = BUTTON_MODES[name]
        note = int(control[3:]) - 1
        active = deck_condition(deck, f"({mode_state})")
        timer = f"stem{deck}"
        # Slider en la definicion: solo al apretar (al soltar VirtualDJ volveria a correr el toggle y lo desharia)
        pad_lines.append(
            f"\t<map value=\"{control}\" action=\"param_bigger 0.5 ? ({deck_action(deck, mode_action)} &amp; "
            f"set '$stem{deck}' {code} &amp; repeat_stop '{timer}' &amp; repeat_start '{timer}' {STEM_DISPLAY_TIME} 1 "
            f"&amp; set '$stem{deck}' 0) : nothing\" />")
        for state, velocity, condition in (("ON", 0x7F, active), ("OFF", 0x00, f"{active} ? false : true")):
            device_lines.append(f'  <sysex value="91{note:02X}{velocity:02X}" name="LED_{control}_{state}" />')
            led_lines.append(f"\t<map value=\"LED_{control}_{state}\" action=\"{condition}\" />")

    def insert_after_line(text, marker, lines):
        start = text.index(marker)
        end = text.index("\n", start) + 1
        return text[:end] + "\n".join(lines) + "\n" + text[end:]

    device = insert_after_line(device, "  <!-- LEDs de los pads:", device_lines)
    start = mapper.index("\t<!-- LEDs de los pads:")
    end = mapper.index("-->\n", start) + 4
    mapper = mapper[:end] + "\n".join(led_lines) + "\n" + mapper[end:]
    mapper = insert_after_line(mapper, '\t<map value="STEP" ', pad_lines)

    # info mode for the other buttons: codes 1..n
    for control, (text, is_slider) in HELP_BUTTONS.items():
        code = help_code(text)
        found = re.search(rf'\t<map value="{control}" action="([^"]*)" />', mapper)
        if not found:
            raise SystemExit(f"Error: no hay mapeo para {control}")
        original = strip_select(found[1])
        catch = f"param_bigger 0.5 ? set '$help' {code} : nothing" if is_slider else f"set '$help' {code}"
        wrapped = f"{SELECT_PREFIX}{catch}) : ({original})"
        mapper = mapper.replace(found[0], f'\t<map value="{control}" action="{wrapped}" />')

    # each deck's screen shows the stem just touched: name on top, ON / OFF below
    for deck in DECK_COLUMNS:
        stem_prefix = f"var '$stem{deck}' 0 ? ("
        top, bottom = "get_text ' '", "get_text ' '"
        for code in range(len(STEMS), 0, -1):
            entry = STEMS[code - 1]
            if entry[2] is None:
                continue
            on, name = entry[3], entry[6]
            state = f"{deck_condition(deck, on)} ? get_text 'ON' : get_text 'OFF'" if on else "get_text 'TODOS ON'"
            top = f"var '$stem{deck}' {code} ? get_text '{name}' : ({top})"
            bottom = f"var '$stem{deck}' {code} ? ({state}) : ({bottom})"
        top = f"var '$stem{deck}' {LOOP_DISPLAY_CODE} ? get_text 'LOOP' : ({top})"
        for name, (_, mode_state, code) in BUTTON_MODES.items():
            top = f"var '$stem{deck}' {code} ? get_text '{name}' : ({top})"
            bottom = (f"var '$stem{deck}' {code} ? (({deck_condition(deck, mode_state)}) ? get_text 'ON' : get_text 'OFF') "
                      f": ({bottom})")
        bottom = (f"var '$stem{deck}' {LOOP_DISPLAY_CODE} ? get_text &quot;`deck {deck} get_loop &amp; param_cast 'text' 6` BEATS&quot; "
                  f": ({bottom})")
        for field, shown in ((f"LCD_TITLE_D{deck}", top), (f"LCD_BOTTOM_D{deck}", bottom)):
            found = re.search(rf'\t<map value="{field}" action="var \'\$vdj\' \? \((.*)\) : get_text \'\'" />', mapper)
            inner = found[1]
            select_part = None
            if inner.startswith(SELECT_PREFIX):
                close = matching_paren(inner, len(SELECT_PREFIX) - 1)
                select_part = inner[len(SELECT_PREFIX):close]
                inner = strip_select(inner)
            if inner.startswith(stem_prefix):
                close = matching_paren(inner, len(stem_prefix) - 1)
                inner = inner[len(stem_prefix):close]
            inner = f"{stem_prefix}{inner}) : ({shown})"
            if select_part is not None:
                inner = f"{SELECT_PREFIX}{select_part}) : ({inner})"
            mapper = mapper.replace(found[0], f"\t<map value=\"{field}\" action=\"var '$vdj' ? ({inner}) : get_text ''\" />")

    # left screen: name on top, empty bottom line while SELECT is held
    chain = f"get_text '{HELP_IDLE}'"
    for code in sorted(help_texts, reverse=True):
        chain = f"var '$help' {code} ? get_text '{help_texts[code]}' : ({chain})"
    for field, shown in (("LCD_TITLE_D1", chain), ("LCD_BOTTOM_D1", "get_text ' '")):
        found = re.search(rf'\t<map value="{field}" action="var \'\$vdj\' \? \((.*)\) : get_text \'\'" />', mapper)
        inner = strip_select(found[1])
        mapper = mapper.replace(found[0], f"\t<map value=\"{field}\" action=\"var '$vdj' ? ({SELECT_PREFIX}{shown}) : ({inner})) : get_text ''\" />")

    names = {element.get("name") for element in ET.fromstring(device.encode("utf-8"))}
    root = ET.fromstring(mapper.encode("utf-8"))
    values = [element.get("value") for element in root]
    unknown = [v for v in values if v not in names and v != "ONINIT"]
    duplicates = sorted({v for v in values if values.count(v) > 1})
    unmapped = sorted(n for n in names if n and n.startswith("LED") and n not in values)
    unbalanced = [e.get("value") for e in root if e.get("action").count("(") != e.get("action").count(")")]
    too_long = [t for t in help_texts.values() if len(t) > 28]
    if unknown or duplicates or unmapped or unbalanced or too_long or "\\" in mapper:
        raise SystemExit(f"Error: desconocidos={unknown} duplicados={duplicates} sin mapear={unmapped} "
                         f"parentesis={unbalanced} textos largos={too_long}")
    return device, mapper, f"{len(pad_lines)} pads, {len(device_lines)} mensajes de LED, {len(help_texts)} nombres de info"


def build():
    """Los dos XML como tienen que quedar, armados desde las fuentes (no escribe nada)."""
    return generate(open(SOURCE_DEVICE, encoding="utf-8").read(), read_source_mapper())


def main():
    device, mapper, summary = build()
    outputs = ((DEVICE, device), (MAPPER, mapper))
    if "--revisar" in sys.argv:
        stale = [path for path, text in outputs if open(path, encoding="utf-8").read() != text]
        for path in stale:
            print(f"Desactualizado: {os.path.relpath(path, HERE)} (corré python generar.py)")
        return 1 if stale else 0
    for path, text in outputs:
        open(path, "w", encoding="utf-8", newline="\n").write(text)
    print(f"OK: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
