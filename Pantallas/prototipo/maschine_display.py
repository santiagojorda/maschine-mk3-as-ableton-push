"""Envía imágenes a las dos pantallas de la Maschine MK3 por USB.

Protocolo tomado de ni-controllers-lib (lib/components/output/ni_lcd_displays.ts):
interfaz 5, endpoint bulk 0x04, 2 pantallas de 480x272, píxeles RGB565 big endian.

Solo toma la interfaz 5. No llama a set_configuration para no resetear las
interfaces que sigue usando el programa de NI.
"""

import struct
import sys
import time

import libusb_package
import logging

import numpy as np
import usb.core
import usb.util

VENDOR_ID = 0x17CC
PRODUCT_ID = 0x1600
DISPLAY_INTERFACE = 5
DISPLAY_ENDPOINT = 0x04
WIDTH = 480
HEIGHT = 272
NUM_DISPLAYS = 2

_BLIT = b"\x03\x00\x00\x00"
_END = b"\x40\x00\x00\x00"


def rgb_to_rgb565(rgb):
    """Convierte un array (alto, ancho, 3) uint8 en bytes RGB565 big endian."""
    r = (rgb[..., 0].astype(np.uint16) & 0xF8) << 8
    g = (rgb[..., 1].astype(np.uint16) & 0xFC) << 3
    b = rgb[..., 2] >> 3
    r |= g
    r |= b
    if sys.byteorder == "little":
        r = r.byteswap()
    return r.tobytes()


def build_frame(display, x, y, width, height, pixels):
    """Arma el paquete de un rectángulo: cabecera, comando, píxeles, dibujar y fin."""
    num_pixels = width * height
    if num_pixels % 2:
        raise ValueError("ancho x alto tiene que ser par")
    if len(pixels) != num_pixels * 2:
        raise ValueError(f"se esperaban {num_pixels * 2} bytes de píxeles, llegaron {len(pixels)}")

    header = bytearray(16)
    header[0] = 0x84
    header[2] = display
    header[3] = 0x60
    struct.pack_into(">HHHH", header, 8, x, y, width, height)

    # 24 bits big endian con la mitad de los píxeles; el primer byte es el comando (0)
    command = b"\x00" + struct.pack(">I", num_pixels // 2)[1:]

    return bytes(header) + command + pixels + _BLIT + _END


def changed_rects(previous, current, strips=4):
    """Rectángulos (x, y, ancho, alto) que cambiaron, uno por franja vertical como máximo.

    x y el ancho quedan pares, así ancho x alto siempre es par (lo pide el protocolo).
    """
    if previous is current or np.array_equal(previous, current):
        return []
    diff = np.any(previous != current, axis=2)
    strip_width = WIDTH // strips
    rects = []
    for strip in range(strips):
        left = strip * strip_width
        part = diff[:, left:left + strip_width]
        rows = np.flatnonzero(part.any(axis=1))
        if rows.size == 0:
            continue
        columns = np.flatnonzero(part.any(axis=0))
        x0 = (left + columns[0]) & ~1
        x1 = min(WIDTH, (left + columns[-1] + 2) & ~1)
        rects.append((int(x0), int(rows[0]), int(x1 - x0), int(rows[-1] + 1 - rows[0])))
    return rects


log = logging.getLogger("usb")


class MaschineDisplays:
    def __init__(self, timeout_ms=1000):
        self.timeout_ms = timeout_ms
        self.device = None
        self._open()

    def _open(self):
        backend = libusb_package.get_libusb1_backend()
        self.device = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID, backend=backend)
        if self.device is None:
            raise RuntimeError(
                "No se encontró la Maschine MK3 por libusb. ¿Está conectada y la "
                "interfaz 5 tiene WinUSB (Zadig)?"
            )
        usb.util.claim_interface(self.device, DISPLAY_INTERFACE)
        log.info("Pantallas de la Maschine abiertas (interfaz %d)", DISPLAY_INTERFACE)

    def _reopen(self):
        try:
            self.close()
        except Exception:
            self.device = None
        self._open()

    @classmethod
    def wait_for_device(cls, retry_seconds=0.5, on_wait=None):
        """Espera a que la Maschine esté conectada (para arrancar antes de enchufarla).
        on_wait se llama en cada intento (el pulso para supervisor.py)."""
        warned = False
        while True:
            if on_wait:
                on_wait()
            try:
                return cls()
            except (RuntimeError, usb.core.USBError) as error:
                if not warned:
                    log.warning(f"Esperando la Maschine: {error}")
                    warned = True
                time.sleep(retry_seconds)

    def send_rgb(self, display, rgb, x=0, y=0):
        """Dibuja un array (alto, ancho, 3) uint8 en la posición x, y de una pantalla.

        Si la transferencia falla (pasó una vez al cambiar de modo, de forma momentánea),
        reabre la conexión y reintenta una vez; si vuelve a fallar, deja pasar el error.
        """
        height, width = rgb.shape[:2]
        frame = build_frame(display, x, y, width, height, rgb_to_rgb565(rgb))
        if self.device is None:  # se desconectó: se vuelve a buscar (si no está, sale un RuntimeError)
            self._open()
        try:
            self.device.write(DISPLAY_ENDPOINT, frame, self.timeout_ms)
        except usb.core.USBError as error:
            log.warning(f"USB de las pantallas: {error}; reconectando")
            self._reopen()
            self.device.write(DISPLAY_ENDPOINT, frame, self.timeout_ms)

    def send_image(self, display, image):
        """Dibuja una imagen PIL de 480x272 en una pantalla."""
        self.send_rgb(display, np.asarray(image.convert("RGB")))

    def send_changes(self, display, rgb, previous):
        """Manda solo lo que cambió respecto de `previous` (un rectángulo por cada franja de 120 px).

        La Maschine recibe ~5 MB/s: si solo se mueven unos medidores, mandar esas
        franjas en lugar de la pantalla entera da muchos más cuadros por segundo.
        Devuelve cuántos píxeles se mandaron.
        """
        if previous is None or previous.shape != rgb.shape:
            self.send_rgb(display, rgb)
            return WIDTH * HEIGHT
        sent = 0
        for x, y, width, height in changed_rects(previous, rgb):
            self.send_rgb(display, np.ascontiguousarray(rgb[y:y + height, x:x + width]), x, y)
            sent += width * height
        return sent

    def clear(self):
        black = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        for display in range(NUM_DISPLAYS):
            self.send_rgb(display, black)

    def close(self):
        if self.device is None:
            return
        try:
            usb.util.release_interface(self.device, DISPLAY_INTERFACE)
        finally:
            usb.util.dispose_resources(self.device)
            self.device = None
