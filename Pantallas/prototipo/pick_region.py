"""Paso 5: ayuda a elegir las zonas de VirtualDJ que van a cada pantalla.

Para cada pantalla: poné el mouse en la esquina superior izquierda de la zona y
apretá Enter, después en la esquina inferior derecha y Enter. Al final imprime
la zona de cada pantalla para pegar en "regions" de config.json.

Uso: python pick_region.py
"""

import ctypes
import json

from screen_capture import set_dpi_aware


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor_position():
    point = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def pick(label):
    input(f"[{label}] Mouse en la esquina SUPERIOR IZQUIERDA y Enter...")
    left, top = cursor_position()
    input(f"[{label}] Mouse en la esquina INFERIOR DERECHA y Enter...")
    right, bottom = cursor_position()
    return {"left": min(left, right), "top": min(top, bottom),
            "width": abs(right - left), "height": abs(bottom - top)}


def main():
    set_dpi_aware()
    picked = {"left": pick("pantalla izquierda"), "right": pick("pantalla derecha")}
    print()
    for name, region in picked.items():
        print(f'{name}: "regions": [{json.dumps(region)}]')


if __name__ == "__main__":
    main()
