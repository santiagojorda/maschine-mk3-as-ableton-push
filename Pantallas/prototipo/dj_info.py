"""Pantalla derecha del modo DJ: el estado de los dos decks con los datos que manda VirtualDJ (vdj_data.py).

Arriba, un panel por deck (1 a la izquierda, 2 a la derecha): tema, artista, BPM,
BPM original y pitch, y SYNC / PITCH LOCK / LOOP. Abajo, cuatro columnas encima de
las perillas 5-8: volumen deck 1, volumen deck 2, filtro deck 1, filtro deck 2.
Cuando cambia el loop, el sync o el pitch lock de un deck, un pop-up en su panel lo muestra.
"""

import math
import time

from PIL import Image, ImageDraw

from ableton_ui import (ACCENT, BACKGROUND, COLUMN_WIDTH, DIM_TEXT, GROOVE, TEXT, _centered, _fit_text, _font,
                        _text_color_on)
from maschine_display import HEIGHT, WIDTH

DECK_COLORS = ((0, 160, 235), (235, 50, 70))  # como VirtualDJ: deck 1 azul, deck 2 rojo
PANEL_WIDTH = WIDTH // 2
PANEL_HEIGHT = 146
STRIP_HEIGHT = 24
POPUP_SECONDS = 1.3
POPUP_FIELDS = ("loop_length", "loop", "sync", "pitch_lock")
CHIP_OFF = (45, 45, 45)
CHIP_GREEN = (40, 190, 80)
CHIP_ORANGE = (240, 140, 20)


def _loop_text(beats):
    """1/16, 1/8, 1/4, 1/2, 1, 2, 4, 8..."""
    if not beats:
        return "-"
    if beats >= 1:
        return str(round(beats))
    return f"1/{round(1 / beats)}"


def _sync_text(sync):
    return {"M": "MASTER", "S": "SYNC"}.get(sync, "SIN SYNC")


def _filter_text(value):
    if value is None:
        return "-"
    offset = value - 0.5
    if abs(offset) < 0.01:
        return "OFF"
    return f"{'LPF' if offset < 0 else 'HPF'} {round(abs(offset) * 200)}%"


def _chip(draw, x, y, text, fill):
    font = _font(13, True)
    width = draw.textlength(text, font=font) + 12
    draw.rectangle((x, y, x + width, y + 20), fill=fill)
    draw.text((x + 6, y + 3), text, font=font, fill=_text_color_on(fill) if fill != CHIP_OFF else DIM_TEXT)
    return x + width + 5


def _draw_panel(draw, index, deck):
    x0 = index * PANEL_WIDTH
    color = DECK_COLORS[index]
    draw.rectangle((x0 + 2, 0, x0 + PANEL_WIDTH - 3, STRIP_HEIGHT - 1), fill=color)
    title = deck.title if deck.get("loaded", True) else None
    text_x = x0 + 8
    if deck.get("playing"):
        draw.polygon(((text_x, 6), (text_x, 18), (text_x + 10, 12)), fill=_text_color_on(color))
        text_x += 16
    draw.text((text_x, 3), _fit_text(draw, title or f"DECK {index + 1}", _font(15, True), x0 + PANEL_WIDTH - 12 - text_x),
              font=_font(15, True), fill=_text_color_on(color))
    draw.text((x0 + 8, STRIP_HEIGHT + 3), _fit_text(draw, deck.artist or "", _font(13), PANEL_WIDTH - 20),
              font=_font(13), fill=DIM_TEXT)

    bpm, original = deck.get("bpm"), deck.get("bpm_original")
    draw.text((x0 + 8, 46), f"{bpm:.2f}" if bpm else "---", font=_font(32, True), fill=TEXT)
    if bpm and original:
        pitch = (bpm / original - 1) * 100
        draw.text((x0 + 8, 86), f"ORIGINAL {original:.2f}", font=_font(13, True), fill=DIM_TEXT)
        draw.text((x0 + 150, 86), f"{pitch:+.1f}%", font=_font(13, True), fill=ACCENT if abs(pitch) >= 0.05 else DIM_TEXT)

    sync = deck.get("sync")
    x = _chip(draw, x0 + 8, 112, _sync_text(sync), CHIP_GREEN if sync == "S" else CHIP_ORANGE if sync == "M" else CHIP_OFF)
    x = _chip(draw, x, 112, "P.LOCK", CHIP_ORANGE if deck.get("pitch_lock") else CHIP_OFF)
    _chip(draw, x, 112, f"LOOP {_loop_text(deck.get('loop_length'))}", CHIP_GREEN if deck.get("loop") else CHIP_OFF)


def _popup_text(field, deck):
    if field == "loop_length":
        return "LOOP", _loop_text(deck.get("loop_length"))
    if field == "loop":
        return "LOOP", _loop_text(deck.get("loop_length")) if deck.get("loop") else "OFF"
    if field == "sync":
        return "SYNC", _sync_text(deck.get("sync"))
    return "PITCH LOCK", "ON" if deck.get("pitch_lock") else "OFF"


def _draw_popup(draw, index, deck, now):
    recent = [(deck.changed_at[field], field) for field in POPUP_FIELDS
              if now - deck.changed_at.get(field, -POPUP_SECONDS) < POPUP_SECONDS]
    if not recent:
        return
    _, field = max(recent)
    title, value = _popup_text(field, deck)
    x0 = index * PANEL_WIDTH
    box = (x0 + 10, 30, x0 + PANEL_WIDTH - 11, PANEL_HEIGHT - 6)
    draw.rectangle(box, fill=(18, 18, 18), outline=TEXT, width=2)
    color = DECK_COLORS[index]
    draw.rectangle((box[0] + 2, box[1] + 2, box[2] - 2, box[1] + 26), fill=color)
    center = (box[0] + box[2]) // 2
    _centered(draw, title, center, box[1] + 6, _font(15, True), _text_color_on(color), width=box[2] - box[0] - 10)
    _centered(draw, value, center, box[1] + 40, _font(40, True), TEXT, width=box[2] - box[0] - 10)


def _draw_crossfader(draw, crossfader):
    if crossfader is None:
        return
    xf = max(0.0, min(1.0, crossfader))
    # Barra horizontal en la línea divisoria central
    x_start, x_end = 140, 340
    y_mid = PANEL_HEIGHT
    draw.rectangle((x_start, y_mid - 2, 240, y_mid + 2), fill=(0, 60, 100))
    draw.rectangle((240, y_mid - 2, x_end, y_mid + 2), fill=(100, 20, 30))
    draw.line((240, y_mid - 5, 240, y_mid + 5), fill=(140, 140, 140))
    # Etiquetas D1 y D2 a los lados
    draw.text((x_start - 16, y_mid - 7), "1", font=_font(12, True), fill=DECK_COLORS[0])
    draw.text((x_end + 8, y_mid - 7), "2", font=_font(12, True), fill=DECK_COLORS[1])
    # Perilla del fader
    thumb_x = x_start + int(xf * (x_end - x_start))
    draw.rectangle((thumb_x - 4, y_mid - 6, thumb_x + 4, y_mid + 6), fill=(245, 245, 245))
    draw.line((thumb_x, y_mid - 4, thumb_x, y_mid + 4), fill=(20, 20, 20))


def _draw_volume(draw, column, value, label, color):
    x0 = column * COLUMN_WIDTH
    center = x0 + COLUMN_WIDTH // 2
    _centered(draw, f"{round(value * 100)}%" if value is not None else "-", center, PANEL_HEIGHT + 4, _font(16, True), TEXT)
    top, bottom = PANEL_HEIGHT + 28, HEIGHT - 34
    draw.rectangle((center - 3, top, center + 3, bottom), fill=GROOVE)
    if value is not None:
        y = bottom - max(0.0, min(1.0, value)) * (bottom - top)
        draw.rectangle((center - 3, y, center + 3, bottom), fill=color)
        draw.rectangle((center - 16, y - 4, center + 16, y + 4), fill=TEXT)
    _name_strip(draw, x0, label, color)


def _draw_filter(draw, column, value, label, color):
    """Perilla redonda bipolar, como en Ableton: el arco sale del centro (filtro apagado)
    hacia la izquierda (pasa bajos) o la derecha (pasa altos)."""
    x0 = column * COLUMN_WIDTH
    center_x = x0 + COLUMN_WIDTH // 2
    _centered(draw, _filter_text(value), center_x, PANEL_HEIGHT + 4, _font(16, True), TEXT)
    center_y, radius, width = (PANEL_HEIGHT + 28 + HEIGHT - 34) // 2 + 4, 30, 8
    box = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)
    start, end = 135, 405  # 270 grados con el hueco abajo (PIL mide en sentido horario desde las 3)
    draw.arc(box, start, end, fill=GROOVE, width=width)
    if value is not None:
        angle = start + max(0.0, min(1.0, value)) * (end - start)
        middle = (start + end) / 2
        if abs(angle - middle) > 0.5:
            draw.arc(box, min(middle, angle), max(middle, angle), fill=color, width=width)
        rad = math.radians(angle)
        inner, outer = radius * 0.2, radius * 0.75
        draw.line((center_x + inner * math.cos(rad), center_y + inner * math.sin(rad),
                   center_x + outer * math.cos(rad), center_y + outer * math.sin(rad)), fill=TEXT, width=4)
    _name_strip(draw, x0, label, color)


def _name_strip(draw, x0, label, color):
    top = HEIGHT - 28
    draw.rectangle((x0 + 4, top, x0 + COLUMN_WIDTH - 5, top + 24), fill=color)
    _centered(draw, label, x0 + COLUMN_WIDTH // 2, top + 4, _font(15, True), _text_color_on(color))


WARNING = (200, 30, 30)


def _draw_warning(draw, text):
    # Franja roja abajo, sobre los nombres de las perillas: los datos de arriba pueden estar viejos
    top = HEIGHT - 30
    draw.rectangle((0, top, WIDTH - 1, HEIGHT - 1), fill=WARNING)
    _centered(draw, text, WIDTH // 2, top + 6, _font(15, True), (255, 255, 255), width=WIDTH - 12)


def render_decks(data, warning=None):
    """Imagen PIL de 480 x 272 con el estado de los dos decks (data: VdjData, o None si no hay datos).
    warning: aviso en rojo (por ejemplo, VirtualDJ dejó de mandar datos)."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    if data is None:
        draw.text((10, 10), "Sin datos de VirtualDJ", font=_font(18, True), fill=DIM_TEXT)
        return image
    now = time.perf_counter()
    with data.lock:
        decks = data.decks
        crossfader = data.general.get("crossfader")
        for index, deck in enumerate(decks):
            _draw_panel(draw, index, deck)
        draw.line((PANEL_WIDTH, 4, PANEL_WIDTH, PANEL_HEIGHT - 4), fill=(40, 40, 40))
        draw.line((4, PANEL_HEIGHT, WIDTH - 4, PANEL_HEIGHT), fill=(40, 40, 40))
        # Barra del crossfader en el centro
        _draw_crossfader(draw, crossfader)
        # Perillas 5-8: volumen 1, volumen 2, filtro 1, filtro 2
        for index, deck in enumerate(decks):
            _draw_volume(draw, index, deck.get("volume"), f"VOL {index + 1}", DECK_COLORS[index])
            _draw_filter(draw, 2 + index, deck.get("filter"), f"FILTRO {index + 1}", DECK_COLORS[index])
        for index, deck in enumerate(decks):
            _draw_popup(draw, index, deck, now)
    if warning:
        _draw_warning(draw, warning)
    return image
