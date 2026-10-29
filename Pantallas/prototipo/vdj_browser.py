"""Vista browser del modo DJ, en la pantalla derecha: la lista de VirtualDJ que tiene el foco
(carpetas o temas; apretar el encoder la cambia).

Recorta las listas de la captura de la ventana de VirtualDJ (zonas en config.json,
"browser") y muestra solo las filas alrededor de la seleccionada, a un tamaño que se
lee. La fila seleccionada se reconoce por su fondo más claro: VirtualDJ pinta las filas
alternando dos grises oscuros y la seleccionada, más clara; en la lista con el foco,
todavía más clara (76 contra 58), así se sabe cuál mostrar.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from maschine_display import HEIGHT, WIDTH

HEADER_HEIGHT = 24
SELECTED_MIN_BRIGHTNESS = 48  # mediana del gris de una línea de la fila seleccionada (las otras: 19 y 34)
SELECTED_MIN_LINES = 12  # alto mínimo para que no cuente una línea suelta
MAX_SCALE = 1.0  # no agranda: se vería borroso
PLAYED_GUTTER = 30  # columna a la izquierda con la marca de "ya pasado"
PLAYED_RED_MIN_WIDTH = 16  # la raya roja de "ya pasado" cruza todo el ícono; el globo rojo de TIDAL es más angosto
PLAYED = (235, 40, 40)
SONG_ROW_HEIGHT = 48  # dos líneas (título y artista) al lado de la tapa
SONG_ROW_MIN, SONG_ROW_MAX = 28, 60  # alto de una fila de VirtualDJ (para no tomar el espacio vacío de abajo)
TEXT_BAND = 24
SONG_COLUMNS_NEEDED = 5  # separadores 0..5
NOTE_MIN_PIXELS = 20  # píxeles gris claro del ícono de la nota en una fila de tema

DEFAULT_LAYOUT = {
    # Coordenadas de la ventana de VirtualDJ (pantalla completa 1920 x 1200, skin PRO)
    "folders": {"title": "CARPETAS", "top": 596, "height": 592, "columns": [[50, 430]]},
    # Título + artista y BPM; played = columna del ícono, donde VirtualDJ raya en rojo los temas ya pasados.
    # Las columnas se buscan en el encabezado (header_y, entre header_left y header_right): se corren si la
    # lista cambia de ancho. Orden de VirtualDJ: portada, título, artista, duración, BPM...; "columns" queda
    # por si no se encuentran.
    # height llega hasta el borde de la lista (1190): sin la barra de LiveFeedback abajo, la lista ocupa todo
    "songs": {"title": "TEMAS", "top": 618, "height": 572, "columns": [[610, 1030], [1105, 1195]],
              "played": [462, 506], "header_y": 597, "header_left": 480, "header_right": 1440,
              "header_columns": [[1, 3], [4, 5]]},
}

_font_cache = {}


def _font(size):
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype("arialbd.ttf", size)
        except OSError:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def _selected_row(lines):
    """(arriba, abajo, brillo) de la fila seleccionada, en líneas de la lista, o None si no se ve."""
    gray = lines.mean(axis=2)
    medians = np.median(gray, axis=1)
    bright = medians >= SELECTED_MIN_BRIGHTNESS
    best, start = None, None
    for y, on in enumerate(np.append(bright, False)):
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start >= SELECTED_MIN_LINES and (best is None or y - start > best[1] - best[0]):
                best = (start, y)
            start = None
    if best is None:
        return None
    return best[0], best[1], float(np.median(medians[best[0]:best[1]]))


def _row_bounds(lines):
    """Filas de la lista como (arriba, abajo): VirtualDJ alterna el gris de fondo de una fila a la otra."""
    background = np.median(lines.mean(axis=2), axis=1)
    bounds, start = [], 0
    for y in range(1, len(background)):
        if abs(background[y] - background[y - 1]) > 5:
            bounds.append((start, y))
            start = y
    bounds.append((start, len(background)))
    return bounds


def _played_rows(lines, icons):
    """Filas con la raya roja de "ya pasado" en el ícono."""
    red = (icons[..., 0] > 170) & (icons[..., 1] < 70) & (icons[..., 2] < 70)
    line_has_mark = red.sum(axis=1) >= PLAYED_RED_MIN_WIDTH
    return [(top, bottom) for top, bottom in _row_bounds(lines) if line_has_mark[top:bottom].any()]


class BrowserView:
    def __init__(self, layout=None):
        self.layout = layout or DEFAULT_LAYOUT
        self.focus = "songs"
        self._last_center = {}  # si no se ve la selección (por ejemplo, al scrollear) se queda donde estaba

    @staticmethod
    def _separators(window, zone):
        """x de los separadores del encabezado (líneas de 1 px oscuras), o [] si no hay encabezado."""
        if "header_y" not in zone:
            return []
        y, left, right = zone["header_y"], zone["header_left"], zone["header_right"]
        band = window[y:y + 3, left:right].mean(axis=(0, 2))
        return [left + x for x in range(1, len(band) - 1) if band[x] < 30 and band[x - 1] > 40 and band[x + 1] > 40]

    def _columns(self, window, zone):
        """Columnas a mostrar, buscadas por los separadores del encabezado."""
        separators = self._separators(window, zone)
        needed = max(index for pair in zone["header_columns"] for index in pair) if "header_columns" in zone else 0
        if len(separators) <= needed:
            return zone["columns"]
        return [[separators[first], separators[last]] for first, last in zone["header_columns"]]

    def _lines(self, window, name):
        zone = self.layout[name]
        top, height = zone["top"], zone["height"]
        columns = self._columns(window, zone)
        return np.concatenate([window[top:top + height, left:right] for left, right in columns], axis=1)

    def render_focused(self, window):
        """Imagen RGB (numpy) de 480 x 272 con la lista que tiene el foco en VirtualDJ."""
        if window is None:
            return self._render(None, None, self.focus)
        lists = {name: self._lines(window, name) for name in self.layout}
        rows = {name: _selected_row(lines) if lines.size else None for name, lines in lists.items()}
        zone = self.layout[self.focus]
        played = []
        if "played" in zone and lists[self.focus].size:
            left, right = zone["played"]
            played = _played_rows(lists[self.focus], window[zone["top"]:zone["top"] + zone["height"], left:right])
        if all(rows.values()):
            # La selección de la lista con el foco es la más clara; si quedan parecidas, no cambia
            folders, songs = rows["folders"][2], rows["songs"][2]
            if abs(folders - songs) >= 8:
                self.focus = "folders" if folders > songs else "songs"
        if self.focus == "songs":
            separators = self._separators(window, zone)
            if len(separators) > SONG_COLUMNS_NEEDED:
                return self._render_songs(window, zone, separators, rows["songs"])
        return self._render(lists[self.focus], rows[self.focus], self.focus, played)

    def _render_songs(self, window, zone, separators, selected):
        """Temas en filas de dos líneas: la tapa a la izquierda, título arriba y artista abajo, BPM a la derecha.
        Entran menos temas, pero se reconoce cada uno por su tapa. Separadores del encabezado:
        0 | portada | 1 | título | 2 | artista | 3 | duración | 4 | BPM | 5."""
        image = Image.new("RGB", (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(image)
        self._header(draw, "songs")
        top, height = zone["top"], zone["height"]
        cover_x, title_x, artist_x = separators[0] + 1, separators[1], separators[2]
        bpm_x, bpm_end = separators[4], separators[5]
        titles = window[top:top + height, title_x:artist_x]
        # Las filas se separan por el fondo en una franja sin texto (a la izquierda de la duración, que va
        # alineada a la derecha): en la columna del título, un nombre largo tapa el fondo y partía la fila
        strip = window[top:top + height, separators[3] + 2:separators[3] + 14]
        left, right = zone["played"]
        icons = window[top:top + height, left:right]
        # Solo filas con el ícono de la nota (gris claro): así la barra de LiveFeedback no cuenta como tema
        note = (icons.min(axis=2) > 160) & (icons.max(axis=2) - icons.min(axis=2) < 40)
        rows = [(start, end) for start, end in _row_bounds(strip)
                if SONG_ROW_MIN <= end - start <= SONG_ROW_MAX and note[start:end].sum() >= NOTE_MIN_PIXELS]
        if not rows:
            return np.asarray(image)
        brightness = [float(np.median(strip[start:end].mean(axis=2))) for start, end in rows]
        index = self._last_center.get("song_row", 0)
        selected_rows = [i for i, value in enumerate(brightness) if value >= SELECTED_MIN_BRIGHTNESS]
        selected = selected_rows[0] if selected_rows else None
        if selected is not None:
            index = selected
        index = min(index, len(rows) - 1)
        self._last_center["song_row"] = index
        visible = (HEIGHT - HEADER_HEIGHT) // SONG_ROW_HEIGHT
        first = max(0, min(index - visible // 2, len(rows) - visible))
        red = (icons[..., 0] > 170) & (icons[..., 1] < 70) & (icons[..., 2] < 70)
        played_lines = red.sum(axis=1) >= PLAYED_RED_MIN_WIDTH

        def band(start, end, x0, x1):
            # La franja del texto, centrada en la fila (las filas de VirtualDJ miden ~40 px)
            middle = top + (start + end) // 2
            return Image.fromarray(np.ascontiguousarray(window[middle - TEXT_BAND // 2:middle + TEXT_BAND // 2, x0:x1]))

        for slot, (start, end) in enumerate(rows[first:first + visible]):
            y = HEADER_HEIGHT + slot * SONG_ROW_HEIGHT
            background = tuple(int(c) for c in np.median(strip[start:end].reshape(-1, 3), axis=0))
            draw.rectangle((0, y, WIDTH - 1, y + SONG_ROW_HEIGHT - 1), fill=background)
            cover = Image.fromarray(np.ascontiguousarray(window[top + start:top + end, cover_x:title_x]))
            cover_width = round(cover.width * SONG_ROW_HEIGHT / cover.height)
            image.paste(cover.resize((cover_width, SONG_ROW_HEIGHT), Image.BILINEAR), (PLAYED_GUTTER, y))
            text_x = PLAYED_GUTTER + cover_width + 6
            bpm = band(start, end, bpm_x, bpm_end)
            bpm_left = WIDTH - bpm.width
            text_width = max(1, min(artist_x - title_x, bpm_left - text_x - 4))
            image.paste(band(start, end, title_x, title_x + text_width), (text_x, y - 1))
            image.paste(band(start, end, artist_x, artist_x + text_width), (text_x, y + SONG_ROW_HEIGHT - TEXT_BAND + 1))
            image.paste(bpm, (bpm_left, y + (SONG_ROW_HEIGHT - TEXT_BAND) // 2))
            if played_lines[start:end].any():
                middle = y + SONG_ROW_HEIGHT / 2
                draw.ellipse((PLAYED_GUTTER / 2 - 8, middle - 8, PLAYED_GUTTER / 2 + 8, middle + 8), fill=PLAYED)
            if first + slot == selected:
                draw.rectangle((0, y, WIDTH - 1, y + SONG_ROW_HEIGHT - 1), outline=(255, 255, 255), width=2)
        return np.asarray(image)

    def _header(self, draw, name):
        draw.rectangle((0, 0, WIDTH, HEADER_HEIGHT - 1), fill=(28, 28, 28))
        draw.text((8, 3), self.layout[name]["title"], font=_font(16), fill=(235, 235, 235))
        if "played" in self.layout[name]:
            # Leyenda de la marca
            draw.ellipse((WIDTH - 82, 7, WIDTH - 72, 17), fill=PLAYED)
            draw.text((WIDTH - 66, 4), "pasado", font=_font(14), fill=(170, 170, 170))

    def _render(self, lines, row, name, played=()):
        image = Image.new("RGB", (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(image)
        self._header(draw, name)
        gutter = PLAYED_GUTTER if "played" in self.layout[name] else 0
        if lines is None:
            draw.text((8, HEADER_HEIGHT + 10), "VirtualDJ no está a la vista", font=_font(16), fill=(140, 140, 140))
            return np.asarray(image)
        if not lines.size:
            return np.asarray(image)
        center = self._last_center.get(name, 0) if row is None else (row[0] + row[1]) // 2
        self._last_center[name] = center

        # Ancho de la pantalla, sin agrandar; se ven las filas de alrededor de la seleccionada
        area = HEIGHT - HEADER_HEIGHT
        scale = min(MAX_SCALE, (WIDTH - gutter) / lines.shape[1])
        source_height = min(lines.shape[0], int(area / scale))
        first = min(max(center - source_height // 2, 0), lines.shape[0] - source_height)
        crop = Image.fromarray(np.ascontiguousarray(lines[first:first + source_height]))
        size = (round(crop.width * scale), round(crop.height * scale))
        image.paste(crop.resize(size, Image.BILINEAR), (gutter, HEADER_HEIGHT))
        for top, bottom in played:
            y = HEADER_HEIGHT + ((top + bottom) / 2 - first) * scale
            if HEADER_HEIGHT + 6 <= y <= HEIGHT - 6:
                draw.ellipse((gutter / 2 - 8, y - 8, gutter / 2 + 8, y + 8), fill=PLAYED)
        if row is not None:
            # Borde blanco en la fila seleccionada: el gris de VirtualDJ se nota poco en la Maschine
            y0 = HEADER_HEIGHT + (row[0] - first) * scale
            y1 = HEADER_HEIGHT + (row[1] - first) * scale - 1
            draw.rectangle((0, max(y0, HEADER_HEIGHT), gutter + size[0] - 1, min(y1, HEIGHT - 1)), outline=(255, 255, 255), width=2)
        return np.asarray(image)
