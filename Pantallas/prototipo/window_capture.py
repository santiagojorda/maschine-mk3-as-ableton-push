"""Captura la ventana de VirtualDJ aunque esté tapada por otras ventanas.

Usa PrintWindow con PW_RENDERFULLCONTENT: Windows le pide a la ventana que se
dibuje en un bitmap propio, así no importa qué haya encima. No funciona con la
ventana minimizada (Windows no la dibuja).

Las zonas se dan en coordenadas de la ventana (0, 0 = esquina superior
izquierda de VirtualDJ), así no dependen de dónde esté la ventana.
"""

import ctypes
import logging
import ctypes.wintypes as W
import threading
import time

import numpy as np
from PIL import Image

from maschine_display import HEIGHT, WIDTH
from screen_capture import fit_image

PW_RENDERFULLCONTENT = 0x2
DIB_RGB_COLORS = 0
BI_RGB = 0

log = logging.getLogger("captura")
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
# En 64 bits los handles no entran en un int de C: hay que declarar los tipos
user32.GetWindowDC.argtypes = [W.HWND]
user32.GetWindowDC.restype = W.HDC
user32.ReleaseDC.argtypes = [W.HWND, W.HDC]
user32.PrintWindow.argtypes = [W.HWND, W.HDC, W.UINT]
user32.IsWindow.argtypes = [W.HWND]
user32.IsIconic.argtypes = [W.HWND]
user32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
kernel32 = ctypes.windll.kernel32
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.OpenProcess.restype = W.HANDLE
kernel32.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
kernel32.CloseHandle.argtypes = [W.HANDLE]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
gdi32.CreateCompatibleDC.argtypes = [W.HDC]
gdi32.CreateCompatibleDC.restype = W.HDC
gdi32.CreateCompatibleBitmap.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = W.HBITMAP
gdi32.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
gdi32.SelectObject.restype = W.HGDIOBJ
gdi32.DeleteObject.argtypes = [W.HGDIOBJ]
gdi32.DeleteDC.argtypes = [W.HDC]
gdi32.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, ctypes.c_void_p, ctypes.c_void_p, W.UINT]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD),
                ("biBitCount", W.WORD), ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD),
                ("biClrImportant", W.DWORD)]


def find_window(process_name="virtualdj.exe", title="VirtualDJ"):
    """La ventana principal visible del proceso (por título)."""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buffer, 256)
            if buffer.value == title:
                found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


class WindowCapture:
    def __init__(self, title="VirtualDJ"):
        self.title = title
        self.hwnd = None

    def _window(self):
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            self.hwnd = find_window(title=self.title)
        return self.hwnd

    def grab_window(self):
        """Imagen RGB (numpy) de toda la ventana, o None si no está o está minimizada."""
        hwnd = self._window()
        if not hwnd or user32.IsIconic(hwnd):
            return None
        rect = W.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None

        window_dc = user32.GetWindowDC(hwnd)
        memory_dc = gdi32.CreateCompatibleDC(window_dc)
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        previous = gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not user32.PrintWindow(hwnd, memory_dc, PW_RENDERFULLCONTENT):
                return None
            header = BITMAPINFOHEADER()
            header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            header.biWidth, header.biHeight = width, -height  # negativo = filas de arriba a abajo
            header.biPlanes, header.biBitCount, header.biCompression = 1, 32, BI_RGB
            buffer = ctypes.create_string_buffer(width * height * 4)
            gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), DIB_RGB_COLORS)
            bgra = np.frombuffer(buffer, dtype=np.uint8).reshape(height, width, 4)
            return bgra[..., 2::-1].copy()  # BGRA -> RGB
        finally:
            gdi32.SelectObject(memory_dc, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(hwnd, window_dc)

    def process_started(self):
        """Hora (time.time) en que arrancó el proceso de la ventana, o None si no está."""
        hwnd = self._window()
        if not hwnd:
            return None
        if getattr(self, "_started_hwnd", None) == hwnd:
            return self._started
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None
        try:
            times = [W.FILETIME() for _ in range(4)]
            if not kernel32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                return None
            created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            # FILETIME: centenas de ns desde 1601
            self._started_hwnd, self._started = hwnd, created / 1e7 - 11644473600
            return self._started
        finally:
            kernel32.CloseHandle(handle)

    def close(self):
        pass


def slot_heights(regions, height):
    """Alto de la franja de cada zona: "slot" si lo tiene (en píxeles de la pantalla); las demás se
    reparten lo que queda en partes iguales."""
    fixed = sum(region.get("slot", 0) for region in regions)
    free = [region for region in regions if "slot" not in region]
    share = (height - fixed) // len(free) if free else 0
    return [region.get("slot", share) for region in regions]


def stack_regions(window, regions, fit, height=HEIGHT):
    """Recorta zonas de una captura de la ventana y las apila de arriba a abajo en 480 x height.
    Cada zona puede tener su propio "fit" y su alto ("slot")."""
    canvas = Image.new("RGB", (WIDTH, height))
    if not regions or window is None:
        return np.asarray(canvas)
    y = 0
    for region, slot in zip(regions, slot_heights(regions, height)):
        left, top = region["left"], region["top"]
        crop = window[top:top + region["height"], left:left + region["width"]]
        if crop.size and slot > 0:
            canvas.paste(fit_image(Image.fromarray(crop), region.get("fit", fit), WIDTH, slot), (0, y))
        y += slot
    return np.asarray(canvas)


class BackgroundWindowCapture:
    """Captura la ventana en un hilo aparte y guarda la última imagen.

    Así capturar (~35 ms) y mandar a la Maschine por USB (~50 ms) van en paralelo,
    y las dos pantallas recortan su zona de la misma captura.
    """

    def __init__(self, fps, title="VirtualDJ"):
        self._capture = WindowCapture(title)
        self._interval = 1.0 / fps
        self._lock = threading.Lock()
        self._latest = None
        self._active = threading.Event()
        self._running = True
        self.captures = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def set_active(self, active):
        """Solo captura en modo DJ, para no gastar CPU en modo Ableton."""
        if active:
            self._active.set()
        else:
            self._active.clear()

    def _loop(self):
        while self._running:
            if not self._active.wait(timeout=0.2):
                continue
            start = time.perf_counter()
            try:
                image = self._capture.grab_window()
            except Exception as error:  # una captura fallida no corta el hilo
                log.error("Error capturando la ventana", exc_info=True)
                image = None
            with self._lock:
                self._latest = image
                self.captures += 1
            time.sleep(max(0.0, self._interval - (time.perf_counter() - start)))

    def process_started(self):
        return self._capture.process_started()

    def latest(self):
        """Última captura de toda la ventana (numpy RGB), o None."""
        with self._lock:
            return self._latest

    def grab_stack(self, regions, fit, height=HEIGHT):
        return stack_regions(self.latest(), regions, fit, height)

    def close(self):
        self._running = False
        self._active.set()
