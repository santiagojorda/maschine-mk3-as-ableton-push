"""Dibuja el modo Ableton con gráficos: faders en el mixer y knobs en los dispositivos.

Usa el estado JSON que manda el script CustomMaschineMK3 (ver ableton_text.py).
Cada pantalla tiene 4 columnas de 120 px, una por perilla (izquierda: perillas
1-4, derecha: 5-8), así cada control queda arriba de su perilla.

Las vistas que no son mixer ni dispositivo (clip, browser, settings...) y los
modos del encoder (volumen master, tempo...) se siguen mostrando con texto.
"""

import math
import time

from PIL import Image, ImageDraw, ImageFont

from maschine_display import HEIGHT, WIDTH

MIXER_VIEW = "default"
DEVICE_VIEW = "device"
BROWSER_VIEW = "browser"
GRAPHIC_VIEWS = (MIXER_VIEW, DEVICE_VIEW)
# Modos del encoder grande que tapan la pantalla con su valor (escala): ahí va texto.
# VOLUME, SWING y TEMPO se dibujan en la pantalla derecha (encoder_view.py); los demás dejan ver los gráficos.
TEXT_ENCODER_MODES = ("scale",)

COLUMNS = 4
COLUMN_WIDTH = WIDTH // COLUMNS
HEADER_HEIGHT = 28

BACKGROUND = (0, 0, 0)
HEADER_BACKGROUND = (28, 28, 28)
TEXT = (235, 235, 235)
DIM_TEXT = (140, 140, 140)
GROOVE = (55, 55, 55)
ACCENT = (255, 150, 30)  # naranja de Ableton para valores
TOUCHED = (255, 255, 255)
METER_GREEN = (60, 200, 90)
METER_YELLOW = (230, 200, 40)
METER_RED = (230, 50, 40)
DEFAULT_TRACK_COLOR = (120, 120, 120)

_fonts = {}


def _font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        try:
            _fonts[key] = ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
        except OSError:
            _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def screen_kind(state):
    """Qué dibujar: "session" (grilla de clips), "browser", "controls" (faders / knobs) o None (texto)."""
    if state is None:
        return None
    # ARRANGER prende la vista session: se ve la grilla hasta apretar otro botón de vista
    if state.get("session_view") and state.get("session"):
        return "session"
    if state.get("encoder_mode") in TEXT_ENCODER_MODES:
        return None
    if state.get("view") == BROWSER_VIEW and state.get("browser"):
        return "browser"
    if state.get("view") in GRAPHIC_VIEWS:
        return "controls"
    return None


def wants_graphics(state):
    return screen_kind(state) is not None


def _track_rgb(color):
    if color is None:
        return DEFAULT_TRACK_COLOR
    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


def _text_color_on(rgb):
    return (0, 0, 0) if sum(rgb) > 380 else (255, 255, 255)


def _fit_text(draw, text, font, width):
    text = text or ""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "..", font=font) > width:
        text = text[:-1]
    return text + ".."


def _centered(draw, text, center_x, y, font, fill, width=COLUMN_WIDTH - 8):
    text = _fit_text(draw, text, font, width)
    draw.text((center_x - draw.textlength(text, font=font) / 2, y), text, font=font, fill=fill)


def _header(draw, left_text, right_text=None, color=None):
    draw.rectangle((0, 0, WIDTH, HEADER_HEIGHT - 1), fill=HEADER_BACKGROUND)
    x = 8
    if color is not None:
        draw.rectangle((8, 7, 21, 20), fill=color)
        x = 28
    draw.text((x, 5), _fit_text(draw, left_text, _font(17, True), WIDTH - x - 120), font=_font(17, True), fill=TEXT)
    if right_text:
        width = draw.textlength(right_text, font=_font(15))
        draw.text((WIDTH - 8 - width, 7), right_text, font=_font(15), fill=DIM_TEXT)


def _meter_color(level):
    if level > 0.92:
        return METER_RED
    if level > 0.75:
        return METER_YELLOW
    return METER_GREEN


def _draw_mute_solo_badges(draw, x0, knob):
    """Insignias visuales de MUTE y SOLO para cada canal en la vista mixer:
    - MUTE: píldora naranja/roja brillante si está silenciado; píldora oscura 'M' si no está silenciado.
    - SOLO: píldora azul eléctrica brillante si está en solo/preescucha; píldora oscura 'S' si no está en solo.
    """
    badge_top = 224
    badge_bottom = 242
    font = _font(11, True)

    # MUTE: x0 + 12 hasta x0 + 56 (ancho 44 px)
    bx0, bx1 = x0 + 12, x0 + 56
    is_mute = bool(knob.get("mute"))
    if is_mute:
        draw.rounded_rectangle((bx0, badge_top, bx1, badge_bottom), radius=3, fill=(235, 75, 25))
        _centered(draw, "MUTE", (bx0 + bx1) // 2, badge_top + 2, font, (255, 255, 255), width=42)
    else:
        draw.rounded_rectangle((bx0, badge_top, bx1, badge_bottom), radius=3, fill=(26, 26, 26), outline=(55, 55, 55))
        _centered(draw, "M", (bx0 + bx1) // 2, badge_top + 2, font, (115, 115, 115), width=42)

    # SOLO: x0 + 64 hasta x0 + 108 (ancho 44 px)
    sx0, sx1 = x0 + 64, x0 + 108
    is_solo = bool(knob.get("solo"))
    if is_solo:
        draw.rounded_rectangle((sx0, badge_top, sx1, badge_bottom), radius=3, fill=(0, 135, 235))
        _centered(draw, "SOLO", (sx0 + sx1) // 2, badge_top + 2, font, (255, 255, 255), width=42)
    else:
        draw.rounded_rectangle((sx0, badge_top, sx1, badge_bottom), radius=3, fill=(26, 26, 26), outline=(55, 55, 55))
        _centered(draw, "S", (sx0 + sx1) // 2, badge_top + 2, font, (115, 115, 115), width=42)


def _draw_fader(draw, column, knob, touched):
    x0 = column * COLUMN_WIDTH
    center = x0 + COLUMN_WIDTH // 2
    color = _track_rgb(knob.get("color"))
    has_badges = "mute" in knob or "solo" in knob
    is_mute = bool(knob.get("mute"))

    # Valor arriba; abajo, cerca de la perilla, el nombre del track sobre una franja de su color
    _centered(draw, knob.get("text"), center, HEADER_HEIGHT + 6, _font(17, True), TOUCHED if touched else TEXT)

    if has_badges:
        name_top = 246
        badge_top = 224
        area_bottom = badge_top - 6
        _draw_mute_solo_badges(draw, x0, knob)
    else:
        name_top = HEIGHT - 30
        area_bottom = name_top - 8

    track_strip_color = _dim(color, 0.45) if is_mute else color
    draw.rectangle((x0 + 4, name_top, x0 + COLUMN_WIDTH - 5, name_top + 23), fill=track_strip_color)
    text_color = _text_color_on(track_strip_color) if not is_mute else (180, 180, 180)
    _centered(draw, knob.get("track") or knob.get("name"), center, name_top + 3, _font(15, True), text_color)

    area_top = HEADER_HEIGHT + 34
    value = max(0.0, min(1.0, knob.get("value", 0.0)))

    if knob.get("bipolar"):
        # Paneo: barra horizontal desde el centro
        y = (area_top + area_bottom) // 2
        left, right = x0 + 14, x0 + COLUMN_WIDTH - 14
        draw.rectangle((left, y - 3, right, y + 3), fill=GROOVE)
        position = left + value * (right - left)
        middle = (left + right) / 2
        fill_color = _dim(ACCENT, 0.5) if is_mute else ACCENT
        draw.rectangle((min(middle, position), y - 6, max(middle, position), y + 6), fill=fill_color)
        draw.rectangle((position - 3, y - 12, position + 3, y + 12), fill=TOUCHED if touched else ((120, 120, 120) if is_mute else TEXT))
    else:
        # Fader: canal con el relleno del valor y la perilla del fader
        groove_x = center - 14
        draw.rectangle((groove_x - 3, area_top, groove_x + 3, area_bottom), fill=GROOVE)
        y = area_bottom - value * (area_bottom - area_top)
        fader_fill = _dim(color, 0.45) if is_mute else color
        draw.rectangle((groove_x - 3, y, groove_x + 3, area_bottom), fill=fader_fill)
        cap_fill = TOUCHED if touched else ((110, 110, 110) if is_mute else (200, 200, 200))
        draw.rectangle((groove_x - 14, y - 5, groove_x + 14, y + 5), fill=cap_fill)

    # Medidor de nivel del track
    if "meter" in knob:
        meter_x = center + 18
        level = max(0.0, min(1.0, knob["meter"]))
        draw.rectangle((meter_x, area_top, meter_x + 10, area_bottom), fill=(25, 25, 25))
        if level > 0:
            y = area_bottom - level * (area_bottom - area_top)
            meter_col = _dim(_meter_color(level), 0.5) if is_mute else _meter_color(level)
            draw.rectangle((meter_x, y, meter_x + 10, area_bottom), fill=meter_col)

    if touched:
        draw.rectangle((x0 + 2, HEADER_HEIGHT + 1, x0 + COLUMN_WIDTH - 3, HEIGHT - 2), outline=TOUCHED, width=2)


def _draw_knob(draw, column, knob, touched, color, label, meter=None):
    """Knob con arco del color del track: valor arriba, nombre abajo sobre una franja de ese color.

    En el mixer (paneo, envíos) label es el track y va su medidor al costado; en un
    dispositivo, label es el nombre del parámetro.
    """
    x0 = column * COLUMN_WIDTH
    center_x = x0 + COLUMN_WIDTH // 2
    has_badges = "mute" in knob or "solo" in knob
    is_mute = bool(knob.get("mute"))

    _centered(draw, knob.get("text"), center_x, HEADER_HEIGHT + 6, _font(17, True), TOUCHED if touched else TEXT)

    if has_badges:
        name_top = 246
        badge_top = 224
        area_bottom = badge_top - 6
        _draw_mute_solo_badges(draw, x0, knob)
    else:
        name_top = HEIGHT - 30
        area_bottom = name_top - 8

    track_strip_color = _dim(color, 0.45) if is_mute else color
    draw.rectangle((x0 + 4, name_top, x0 + COLUMN_WIDTH - 5, name_top + 23), fill=track_strip_color)
    text_color = _text_color_on(track_strip_color) if not is_mute else (180, 180, 180)
    _centered(draw, label, center_x, name_top + 3, _font(15, True), text_color)

    if meter is not None:
        meter_x, top, bottom = x0 + COLUMN_WIDTH - 16, HEADER_HEIGHT + 34, area_bottom
        level = max(0.0, min(1.0, meter))
        draw.rectangle((meter_x, top, meter_x + 8, bottom), fill=(25, 25, 25))
        if level > 0:
            meter_col = _dim(_meter_color(level), 0.5) if is_mute else _meter_color(level)
            draw.rectangle((meter_x, bottom - level * (bottom - top), meter_x + 8, bottom), fill=meter_col)
        center_x -= 8

    center_y, radius = (136 if has_badges else 144), (38 if has_badges else 40)
    box = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)
    start, end = 135, 405  # 270 grados, con el hueco abajo (PIL mide en sentido horario desde las 3)
    value = max(0.0, min(1.0, knob.get("value", 0.0)))
    angle = start + value * (end - start)
    width = 8 if has_badges else 9
    arc_color = _dim(_visible(color), 0.5) if is_mute else _visible(color)
    draw.arc(box, start, end, fill=GROOVE, width=width)
    if knob.get("bipolar"):
        middle = (start + end) / 2
        if angle != middle:
            draw.arc(box, min(middle, angle), max(middle, angle), fill=arc_color, width=width)
    elif angle > start:
        draw.arc(box, start, angle, fill=arc_color, width=width)

    # Indicador desde el centro
    rad = math.radians(angle)
    inner, outer = radius * 0.25, radius * 0.75
    draw.line((center_x + inner * math.cos(rad), center_y + inner * math.sin(rad),
               center_x + outer * math.cos(rad), center_y + outer * math.sin(rad)),
              fill=TOUCHED if touched else ((120, 120, 120) if is_mute else TEXT), width=4)

    if touched:
        draw.rectangle((x0 + 2, HEADER_HEIGHT + 1, x0 + COLUMN_WIDTH - 3, HEIGHT - 2), outline=TOUCHED, width=2)


def _visible(rgb):
    """Un color de track muy oscuro no se ve sobre negro: se aclara lo justo."""
    brightness = max(rgb)
    if brightness >= 90:
        return rgb
    if brightness == 0:
        return (90, 90, 90)
    scale = 90 / brightness
    return tuple(min(255, int(channel * scale)) for channel in rgb)


def _is_volume(knob):
    return "volume" in (knob.get("name") or "").lower()


SESSION_ROWS = 4
TRACK_STRIP_HEIGHT = 26
EMPTY_SLOT = (30, 30, 30)
PLAYING = (60, 220, 90)
PADS_FRAME = (0, 230, 80)  # marco de las columnas que están en los pads
PADS_FRAME_WIDTH = 4
RECORDING = (230, 50, 40)
PLAYING_BORDER = PLAYING  # borde verde de los clips que suenan; el blanco queda para el clip seleccionado
SESSION_TEXT = (0, 0, 0)  # en session todo el texto va en negro...
TARGET_TEXT = (255, 255, 255)  # ...menos el del track seleccionado o fijado
BLINK_SECONDS = 0.25


def _dim(rgb, factor):
    return tuple(int(channel * factor) for channel in rgb)


def _draw_clip(draw, box, slot, dim, text_color):
    x0, y0, x1, y1 = box
    if slot is None:
        return
    if slot.get("empty"):
        draw.rectangle(box, fill=_dim(EMPTY_SLOT, dim))
        if slot.get("triggered") and int(time.perf_counter() / BLINK_SECONDS) % 2:
            draw.rectangle(box, outline=TEXT, width=2)
        return
    color = _dim(_track_rgb(slot.get("color")), dim)
    blink_off = slot.get("triggered") and int(time.perf_counter() / BLINK_SECONDS) % 2
    draw.rectangle(box, fill=_dim(color, 0.45) if blink_off else color)
    left = x0 + 6
    if slot.get("recording"):
        draw.ellipse((x0 + 6, y0 + 7, x0 + 18, y0 + 19), fill=RECORDING, outline=(255, 255, 255))
        left = x0 + 24
    elif slot.get("playing"):
        draw.polygon(((x0 + 7, y0 + 6), (x0 + 7, y0 + 20), (x0 + 19, y0 + 13)), fill=text_color)
        left = x0 + 24
    font = _font(15, True)
    name = _fit_text(draw, slot.get("name") or "", font, x1 - left - 4)
    draw.text((left, y0 + 5), name, font=font, fill=text_color)
    if slot.get("playing") or slot.get("recording"):
        # Verde: los clips que suenan; el blanco queda para el clip seleccionado
        draw.rectangle(box, outline=PLAYING_BORDER if slot.get("playing") else RECORDING, width=3)


def render_session(state, display, pads_frame=True):
    """Grilla de clips: un bloque de 8 tracks (4 por pantalla) x 4 escenas. Las columnas que están en los
    pads se ven normales y las demás, más tenues; mover los pads dentro del bloque solo mueve el resaltado.
    pads_frame=False: sin el marco verde (la grilla al lado del browser)."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    session = state.get("session") or {}
    tracks = session.get("tracks") or []
    ring_start = session.get("ring_column", 0)
    ring_end = ring_start + session.get("ring_tracks", COLUMNS)
    # Número real del track en el set (empieza en 1)
    first_track = session.get("page_offset", session.get("track_offset", 0)) + 1
    row_height = (HEIGHT - TRACK_STRIP_HEIGHT) // SESSION_ROWS
    for column in range(COLUMNS):
        index = display * COLUMNS + column
        track = tracks[index] if index < len(tracks) else None
        dim = 1.0 if ring_start <= index < ring_end else 0.8
        x0 = column * COLUMN_WIDTH
        if track is None:
            continue
        color = _dim(_track_rgb(track.get("color")), dim)
        draw.rectangle((x0 + 2, 0, x0 + COLUMN_WIDTH - 3, TRACK_STRIP_HEIGHT - 3), fill=color)
        text_color = TARGET_TEXT if track.get("target") else SESSION_TEXT
        label = f"{first_track + index} {track.get('name') or ''}"
        _centered(draw, label, x0 + COLUMN_WIDTH // 2, 4, _font(14, True), text_color)
        slots = track.get("slots") or []
        for row in range(SESSION_ROWS):
            top = TRACK_STRIP_HEIGHT + row * row_height
            box = (x0 + 2, top + 2, x0 + COLUMN_WIDTH - 3, top + row_height - 3)
            slot = slots[row] if row < len(slots) else None
            _draw_clip(draw, box, slot, dim, text_color)
            if slot and slot.get("selected"):
                # El clip seleccionado en Live, como un cursor: borde grueso (verde si suena, rojo si graba,
                # blanco si inactivo) y el nombre invertido (franja blanca, letras negras)
                bx0, by0, bx1, by1 = box
                outline_color = PLAYING_BORDER if slot.get("playing") else (RECORDING if slot.get("recording") else TEXT)
                draw.rectangle((bx0 - 2, by0 - 2, bx1 + 2, by1 + 2), outline=outline_color, width=4)
                draw.rectangle((bx0, by0, bx1, by0 + 22), fill=TEXT)
                name = "vacío" if slot.get("empty") else (slot.get("name") or "")
                font = _font(15, True)
                if slot.get("playing"):
                    draw.polygon(((bx0 + 7, by0 + 5), (bx0 + 7, by0 + 17), (bx0 + 17, by0 + 11)), fill=(0, 0, 0))
                    left = bx0 + 22
                elif slot.get("recording"):
                    draw.ellipse((bx0 + 6, by0 + 5, bx0 + 17, by0 + 16), fill=RECORDING, outline=(0, 0, 0))
                    left = bx0 + 22
                else:
                    left = bx0 + 6
                draw.text((left, by0 + 3), _fit_text(draw, name, font, bx1 - left - 6), font=font, fill=(0, 0, 0))

    # Pop-up chico de la perilla que se toca: tapa las 2 celdas de abajo de su columna.
    # Volumen (flecha izquierda) o un parámetro del dispositivo (flecha derecha)
    knobs = state.get("knobs") or []
    fx_page = session.get("knob_page") == "fx"
    for touched in state["popups"] if "popups" in state else touched_knobs(state):
        if not (0 <= touched < len(knobs) and knobs[touched] and touched // COLUMNS == display):
            continue
        x0 = (touched % COLUMNS) * COLUMN_WIDTH
        top = TRACK_STRIP_HEIGHT + (SESSION_ROWS - 2) * row_height
        box = (x0 + 2, top + 2, x0 + COLUMN_WIDTH - 3, TRACK_STRIP_HEIGHT + SESSION_ROWS * row_height - 3)
        if fx_page:
            device_color = state.get("device_color")
            color = _track_rgb(device_color if device_color is not None else state.get("track_color"))
            _draw_parameter_popup(draw, knobs[touched], box, color)
        else:
            _draw_volume_popup(draw, knobs[touched], box)

    if pads_frame:
        _draw_pads_frame(draw, display, ring_start, ring_end)
    _draw_page_notice(draw, display, session.get("knob_page"), state.get("device"))
    return image


PAGE_NOTICE_SECONDS = 1.5
_page_notice = {"page": None, "time": 0.0}


def _draw_page_notice(draw, display, page, device):
    """Al cambiar con las flechas qué manejan las perillas, un cartel en la pantalla derecha lo dice."""
    if page is None:
        return
    now = time.perf_counter()
    if page != _page_notice["page"]:
        # La primera vez (al entrar a la vista session) no se avisa
        _page_notice["time"] = now if _page_notice["page"] is not None else 0.0
        _page_notice["page"] = page
    if display != 1 or now - _page_notice["time"] > PAGE_NOTICE_SECONDS:
        return
    text = "PERILLAS: VOLUMEN" if page != "fx" else f"PERILLAS: {device or 'FX'}"
    box = (40, HEIGHT // 2 - 30, WIDTH - 40, HEIGHT // 2 + 30)
    draw.rectangle(box, fill=(18, 18, 18), outline=TEXT, width=2)
    _centered(draw, text, WIDTH // 2, HEIGHT // 2 - 14, _font(22, True), TEXT, width=box[2] - box[0] - 16)


def _draw_parameter_popup(draw, knob, box, color):
    """Un parámetro del dispositivo en el recuadro chico: nombre, valor y una perilla redonda."""
    left, top, right, bottom = box
    center = (left + right) // 2
    draw.rectangle(box, fill=(18, 18, 18), outline=TEXT, width=2)
    draw.rectangle((left + 2, top + 2, right - 2, top + 24), fill=color)
    _centered(draw, knob.get("name"), center, top + 5, _font(14, True), _text_color_on(color), width=right - left - 10)
    _centered(draw, knob.get("text"), center, top + 28, _font(17, True), TEXT, width=right - left - 8)
    radius, width = 24, 7
    center_y = (top + 54 + bottom - 6) // 2 + 4
    arc_box = (center - radius, center_y - radius, center + radius, center_y + radius)
    start, end = 135, 405
    value = max(0.0, min(1.0, knob.get("value", 0.0)))
    angle = start + value * (end - start)
    draw.arc(arc_box, start, end, fill=GROOVE, width=width)
    if knob.get("bipolar"):
        middle = (start + end) / 2
        if abs(angle - middle) > 0.5:
            draw.arc(arc_box, min(middle, angle), max(middle, angle), fill=_visible(color), width=width)
    elif angle > start:
        draw.arc(arc_box, start, angle, fill=_visible(color), width=width)
    rad = math.radians(angle)
    draw.line((center + radius * 0.2 * math.cos(rad), center_y + radius * 0.2 * math.sin(rad),
               center + radius * 0.75 * math.cos(rad), center_y + radius * 0.75 * math.sin(rad)), fill=TEXT, width=3)


class PopupTracker:
    """Qué perillas muestran su pop-up: las que se están tocando y, un momento después de soltarlas, las últimas.
    Cada perilla lleva su propio tiempo, así que varias pueden verse a la vez y solaparse."""

    def __init__(self, linger_seconds=0.4):
        self._linger = linger_seconds
        self._last_touched = {}

    def update(self, touched_now, now=None):
        now = time.perf_counter() if now is None else now
        for index in touched_now:
            self._last_touched[index] = now
        self._last_touched = {index: moment for index, moment in self._last_touched.items()
                              if index in touched_now or now - moment < self._linger}
        return sorted(self._last_touched)


def touched_knobs(state):
    """Las perillas que se están tocando: la lista del script más la activa (si la lista llega vacía, la activa vale)."""
    if state.get("no_popup"):
        return []
    knobs = set(state.get("touched_all") or [])
    if state.get("touched", -1) >= 0:
        knobs.add(state["touched"])
    return sorted(knobs)


def _draw_pads_frame(draw, display, ring_start, ring_end):
    """Marco verde alrededor de las columnas que están en los pads. Si siguen en la otra pantalla,
    ese lado queda abierto, así el marco se lee como uno solo entre las dos."""
    first_on_screen = display * COLUMNS
    first = max(ring_start, first_on_screen)
    last = min(ring_end, first_on_screen + COLUMNS) - 1
    if first > last:
        return
    left = (first - first_on_screen) * COLUMN_WIDTH
    right = (last - first_on_screen + 1) * COLUMN_WIDTH - 1
    top, bottom, width = 0, HEIGHT - 1, PADS_FRAME_WIDTH
    draw.rectangle((left, top, right, top + width - 1), fill=PADS_FRAME)
    draw.rectangle((left, bottom - width + 1, right, bottom), fill=PADS_FRAME)
    if first == ring_start:
        draw.rectangle((left, top, left + width - 1, bottom), fill=PADS_FRAME)
    if last == ring_end - 1:
        draw.rectangle((right - width + 1, top, right, bottom), fill=PADS_FRAME)


def _draw_mixer_cursor(draw, display, column):
    """Marco blanco alrededor del track donde está el cursor del mixer (el track seleccionado en Live)."""
    local = column - display * COLUMNS
    if not 0 <= local < COLUMNS:
        return
    left = local * COLUMN_WIDTH + 1
    right = (local + 1) * COLUMN_WIDTH - 2
    draw.rectangle((left, HEADER_HEIGHT + 1, right, HEIGHT - 2), outline=TOUCHED, width=3)


def _draw_volume_popup(draw, knob, box):
    """Volumen de un track en un recuadro chico (box): nombre, valor en dB, fader vertical y medidor."""
    left, top, right, bottom = box
    color = _track_rgb(knob.get("color"))
    center = (left + right) // 2
    draw.rectangle(box, fill=(18, 18, 18), outline=TEXT, width=2)
    draw.rectangle((left + 2, top + 2, right - 2, top + 24), fill=color)
    _centered(draw, knob.get("track") or knob.get("name"), center, top + 5, _font(14, True),
              _text_color_on(color), width=right - left - 10)
    # El valor arriba; debajo, el fader vertical (relleno del color del track y una línea blanca en la
    # posición) con el medidor al lado
    _centered(draw, knob.get("text"), center, top + 28, _font(17, True), TEXT, width=right - left - 8)
    fader_x, meter_x = center - 8, center + 16
    fader_top, fader_bottom = top + 54, bottom - 8
    value = max(0.0, min(1.0, knob.get("value", 0.0)))
    position = fader_bottom - value * (fader_bottom - fader_top)
    draw.rectangle((fader_x - 3, fader_top, fader_x + 3, fader_bottom), fill=GROOVE)
    if position < fader_bottom:
        draw.rectangle((fader_x - 3, position, fader_x + 3, fader_bottom), fill=_visible(color))
    draw.rectangle((fader_x - 12, position - 2, fader_x + 12, position + 2), fill=TOUCHED)
    meter = max(0.0, min(1.0, knob.get("meter") or 0.0))
    draw.rectangle((meter_x - 3, fader_top, meter_x + 3, fader_bottom), fill=(25, 25, 25))
    if meter > 0:
        draw.rectangle((meter_x - 3, fader_bottom - meter * (fader_bottom - fader_top), meter_x + 3, fader_bottom),
                       fill=_meter_color(meter))


BROWSER_ROW_HEIGHT = 30
BROWSER_ROWS = (HEIGHT - HEADER_HEIGHT) // BROWSER_ROW_HEIGHT
FOLDER_ICON = (230, 180, 60)


def _draw_browser_list(draw, listing):
    """Filas de una carpeta del browser con la seleccionada en el medio: franja blanca y letras negras."""
    items = listing.get("items") or []
    first, selected = listing.get("first", 0), listing.get("selected", 0)
    top_index = max(0, min(selected - BROWSER_ROWS // 2, listing.get("count", 0) - BROWSER_ROWS))
    font = _font(17, True)
    for row in range(BROWSER_ROWS):
        index = top_index + row
        if not 0 <= index - first < len(items):
            continue
        item = items[index - first]
        y0 = HEADER_HEIGHT + row * BROWSER_ROW_HEIGHT
        y1 = y0 + BROWSER_ROW_HEIGHT - 1
        is_selected = index == selected
        if is_selected:
            draw.rectangle((0, y0, WIDTH - 1, y1), fill=TEXT)
        elif row % 2:
            draw.rectangle((0, y0, WIDTH - 1, y1), fill=(22, 22, 22))
        text_color = (0, 0, 0) if is_selected else TEXT
        x = 10
        if item.get("folder"):
            # Carpetita
            draw.rectangle((x, y0 + 10, x + 7, y0 + 13), fill=FOLDER_ICON)
            draw.rectangle((x, y0 + 12, x + 17, y0 + 23), fill=FOLDER_ICON)
            x += 26
        draw.text((x, y0 + 5), _fit_text(draw, item.get("name"), font, WIDTH - x - 10), font=font, fill=text_color)


def render_browser(state, display):
    """Browser de Live, como el de VirtualDJ: la lista a la derecha. A la izquierda, la grilla actual de
    la vista session (los 4 tracks de los pads, con su marco verde), para ver dónde va a caer lo que se
    cargue; si la selección sale de los pads, se corren 4 tracks o 1 escena, como en la vista session."""
    browser = state["browser"]
    path = browser.get("path") or []
    if display == 0:
        grid = state.get("browser_grid")
        if not grid:
            return Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        first = grid.get("ring_column", 0)
        grid_state = {"session": {"tracks": (grid.get("tracks") or [])[first:first + COLUMNS],
                                  "page_offset": grid.get("page_offset", 0) + first,
                                  "scene_offset": grid.get("scene_offset", 0), "ring_column": 0,
                                  "ring_tracks": COLUMNS}}
        return render_session(grid_state, 0)
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    listing = browser.get("list") or {}
    count = listing.get("count", 0)
    position = f"{listing.get('selected', 0) + 1}/{count}" if count else "vacía"
    _header(draw, " > ".join(path) if path else "BROWSER", position)
    _draw_browser_list(draw, listing)
    return image


def render_screen(state, display):
    """Imagen PIL de una pantalla (0 = izquierda, 1 = derecha): grilla de session, mixer o dispositivo."""
    kind = screen_kind(state)
    if kind == "session":
        return render_session(state, display)
    if kind == "browser":
        return render_browser(state, display)
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    view = state.get("view")
    track_color = _track_rgb(state.get("track_color"))
    device_color = _track_rgb(state["device_color"]) if state.get("device_color") is not None else track_color

    if display == 0:
        if view == MIXER_VIEW:
            parameter = state.get("mixer_parameter")
            _header(draw, "MIXER", parameter)
        else:
            # El color del dispositivo: el de su cadena si está en un rack, si no el del track
            _header(draw, state.get("device") or "Sin dispositivo", "FX", color=device_color)
    else:
        _header(draw, state.get("track") or "", "LOCK" if state.get("locked") else None, color=track_color)

    knobs = state.get("knobs") or []
    touched = state.get("touched", -1)
    for column in range(COLUMNS):
        index = display * COLUMNS + column
        knob = knobs[index] if index < len(knobs) else None
        if not knob:
            continue
        if view == MIXER_VIEW:
            # Volumen = fader; paneo y envíos = knob
            if _is_volume(knob):
                _draw_fader(draw, column, knob, touched == index)
            else:
                _draw_knob(draw, column, knob, touched == index, _track_rgb(knob.get("color")),
                           knob.get("track") or knob.get("name"), knob.get("meter"))
        else:
            _draw_knob(draw, column, knob, touched == index, device_color, knob.get("name"))
        if column:
            x = column * COLUMN_WIDTH
            draw.line((x, HEADER_HEIGHT + 4, x, HEIGHT - 4), fill=(35, 35, 35))
    frame = state.get("grid_frame")
    if view == MIXER_VIEW and frame:
        # El mixer muestra los tracks de la grilla de session: el mismo marco verde de los que están en los pads
        _draw_pads_frame(draw, display, frame["ring_column"], frame["ring_column"] + frame["ring_tracks"])
        if frame.get("selected") is not None:
            _draw_mixer_cursor(draw, display, frame["selected"])
    return image
