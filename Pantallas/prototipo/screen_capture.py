"""Captura una zona de la pantalla de la PC y la adapta a 480x272."""

import ctypes

import mss
import numpy as np
from PIL import Image

from maschine_display import HEIGHT, WIDTH


def set_dpi_aware():
    """Hace que las coordenadas sean píxeles reales aunque Windows tenga escala (125 %, 150 %...)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()


def fit_image(image, fit, width=WIDTH, height=HEIGHT):
    """Adapta una imagen PIL a width x height (por defecto, la pantalla entera).

    contain = entra entera con bordes negros; cover = llena recortando;
    stretch = llena deformando.
    """
    if fit == "stretch":
        return image.resize((width, height), Image.BILINEAR)

    scale_w = width / image.width
    scale_h = height / image.height
    scale = max(scale_w, scale_h) if fit == "cover" else min(scale_w, scale_h)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(size, Image.BILINEAR)

    canvas = Image.new("RGB", (width, height))
    canvas.paste(resized, ((width - size[0]) // 2, (height - size[1]) // 2))
    return canvas


class RegionCapture:
    """Usar desde un solo hilo: mss en Windows no se puede compartir entre hilos."""

    def __init__(self):
        self._sct = (getattr(mss, "MSS", None) or mss.mss)()

    def _grab_image(self, region):
        shot = self._sct.grab(region)
        bgra = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return Image.fromarray(bgra[..., 2::-1])  # BGRA -> RGB

    def grab(self, region, fit):
        return np.asarray(fit_image(self._grab_image(region), fit))

    def grab_stack(self, regions, fit, height=HEIGHT):
        """Captura varias zonas y las apila de arriba a abajo (480 x height), cada una en una franja igual."""
        canvas = Image.new("RGB", (WIDTH, height))
        if not regions:  # sin zonas: pantalla en negro
            return np.asarray(canvas)
        slot = height // len(regions)
        for index, region in enumerate(regions):
            canvas.paste(fit_image(self._grab_image(region), fit, WIDTH, slot), (0, index * slot))
        return np.asarray(canvas)

    def close(self):
        self._sct.close()
