"""Vista del encoder grande con VOLUME o SWING, igual en Ableton y en VirtualDJ (pantalla derecha);
en Ableton también TEMPO (la barra va de 60 a 200 BPM).

VOLUME = volumen master, SWING = volumen de auriculares (cue), en los dos programas:
título arriba, el valor grande, un fader horizontal con una línea blanca en la
posición y, para el master, el medidor de salida.
"""

from PIL import Image, ImageDraw

from ableton_ui import BACKGROUND, DIM_TEXT, GROOVE, TEXT, _centered, _font, _meter_color, _text_color_on
from maschine_display import HEIGHT, WIDTH

VOLUME = "volume"
SWING = "swing"
TEMPO = "tempo"
TITLES = {VOLUME: "VOLUMEN MASTER", SWING: "AURICULARES", TEMPO: "TEMPO"}
COLORS = {VOLUME: (255, 150, 30), SWING: (0, 170, 230), TEMPO: (170, 90, 230)}


def render_encoder(mode, value, text, source, meter=None):
    """mode: VOLUME o SWING; value 0..1; text: el valor como lo muestra el programa; source: "ABLETON" o "DJ"."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    color = COLORS.get(mode, (120, 120, 120))
    draw.rectangle((0, 0, WIDTH - 1, 39), fill=color)
    text_color = _text_color_on(color)
    draw.text((12, 8), TITLES.get(mode, mode.upper()), font=_font(22, True), fill=text_color)
    width = draw.textlength(source, font=_font(15, True))
    draw.text((WIDTH - 12 - width, 12), source, font=_font(15, True), fill=text_color)

    _centered(draw, text or "-", WIDTH // 2, 62, _font(64, True), TEXT, width=WIDTH - 20)

    # Fader horizontal con la línea blanca en la posición
    left, right, y = 30, WIDTH - 30, 186
    value = max(0.0, min(1.0, value or 0.0))
    position = left + value * (right - left)
    draw.rectangle((left, y - 5, right, y + 5), fill=GROOVE)
    if position > left:
        draw.rectangle((left, y - 5, position, y + 5), fill=color)
    draw.rectangle((position - 3, y - 20, position + 3, y + 20), fill=TEXT)

    if meter is not None:
        level = max(0.0, min(1.0, meter))
        top = y + 34
        draw.rectangle((left, top, right, top + 10), fill=(25, 25, 25))
        if level > 0:
            draw.rectangle((left, top, left + level * (right - left), top + 10), fill=_meter_color(level))
    return image


def _ableton_bpm(text):
    try:
        return float(str(text).split()[0])
    except (ValueError, IndexError):
        return None


def _draw_vdj_tempo(image, ableton_bpm, vdj):
    """El tempo del deck de referencia de VirtualDJ, chico, abajo, para compararlo con el de Ableton.
    vdj: (índice del deck, BPM). Verde si coinciden (menos de 0,05 BPM de diferencia), naranja si no."""
    draw = ImageDraw.Draw(image)
    deck, bpm = vdj
    difference = None if ableton_bpm is None else bpm - ableton_bpm
    same = difference is not None and abs(difference) < 0.05
    color = (80, 210, 120) if same else (255, 170, 60)
    top = HEIGHT - 44
    draw.line((30, top - 6, WIDTH - 30, top - 6), fill=GROOVE)
    draw.text((30, top + 6), f"VDJ  DECK {deck + 1}", font=_font(14, True), fill=DIM_TEXT)
    value = f"{bpm:.2f}"
    width = draw.textlength(value, font=_font(26, True))
    draw.text((WIDTH // 2 - width // 2 + 20, top), value, font=_font(26, True), fill=TEXT)
    note = "IGUAL" if same else (f"{difference:+.2f}" if difference is not None else "")
    width = draw.textlength(note, font=_font(16, True))
    draw.text((WIDTH - 30 - width, top + 8), note, font=_font(16, True), fill=color)


def render_ableton(encoder, vdj=None):
    """encoder: el campo "encoder" del estado del script (mode, value, text, meter).
    vdj: (deck, BPM) del deck de referencia de VirtualDJ, o None; solo se dibuja en el modo TEMPO."""
    image = render_encoder(encoder.get("mode"), encoder.get("value"), encoder.get("text"), "ABLETON", encoder.get("meter"))
    if vdj is not None and encoder.get("mode") == TEMPO:
        _draw_vdj_tempo(image, _ableton_bpm(encoder.get("text")), vdj)
    return image


TEMPO_RANGE = (60.0, 200.0)  # lo mismo que TEMPO_SCREEN_RANGE del script de Ableton


def tempo_encoder(tempo, vdj=None):
    """La vista de tempo (el de Ableton, también cuando se la abre desde el modo DJ). tempo: BPM o None."""
    low, high = TEMPO_RANGE
    value = 0.0 if tempo is None else max(0.0, min(1.0, (tempo - low) / (high - low)))
    return render_ableton({"mode": TEMPO, "value": value, "text": f"{tempo:.2f} BPM" if tempo else "-"}, vdj)


def dj_encoder(data, tempo=None, vdj=None):
    """Imagen de VOLUME / SWING / TEMPO en modo DJ, o None si el encoder está en el browser (data: VdjData).
    tempo: el tempo de Ableton que mandó el script; vdj: (deck, BPM) del deck de referencia."""
    if data is None:
        return None
    with data.lock:
        general = data.general
        if general.get("encoder_mode") == "3":
            return tempo_encoder(tempo, vdj)
        mode = {"1": VOLUME, "2": SWING}.get(general.get("encoder_mode"))
        if mode is None:
            return None
        value = general.get("master_volume" if mode == VOLUME else "headphone_volume")
    return render_encoder(mode, value, f"{round(value * 100)}%" if value is not None else "-", "DJ")
