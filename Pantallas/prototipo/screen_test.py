"""Paso 3: pinta barras de colores en la pantalla 0 y un degradé en la 1, y mide los fps.

Uso: python screen_test.py [--frames 60]
"""

import argparse
import time

import numpy as np

from maschine_display import HEIGHT, WIDTH, MaschineDisplays


def color_bars():
    colors = [
        (255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
        (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0),
    ]
    image = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    bar_width = WIDTH // len(colors)
    for index, color in enumerate(colors):
        image[:, index * bar_width:(index + 1) * bar_width] = color
    return image


def gradient():
    x = np.linspace(0, 255, WIDTH, dtype=np.uint8)
    y = np.linspace(0, 255, HEIGHT, dtype=np.uint8)
    image = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    image[..., 0] = x[np.newaxis, :]
    image[..., 1] = y[:, np.newaxis]
    image[..., 2] = 255 - x[np.newaxis, :]
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=60, help="cuadros a mandar para medir fps")
    args = parser.parse_args()

    displays = MaschineDisplays()
    try:
        bars, grad = color_bars(), gradient()
        displays.send_rgb(0, bars)
        displays.send_rgb(1, grad)
        print("Imagen de prueba enviada: barras a la izquierda, degradé a la derecha.")

        start = time.perf_counter()
        for _ in range(args.frames):
            displays.send_rgb(0, bars)
            displays.send_rgb(1, grad)
        elapsed = time.perf_counter() - start
        print(f"Pantalla completa (las dos): {args.frames / elapsed:.1f} fps")

        half = bars[:HEIGHT // 2]
        start = time.perf_counter()
        for _ in range(args.frames):
            displays.send_rgb(0, half)
            displays.send_rgb(1, half)
        elapsed = time.perf_counter() - start
        print(f"Media pantalla (las dos): {args.frames / elapsed:.1f} fps")

        input("Enter para borrar las pantallas y salir...")
        displays.clear()
    finally:
        displays.close()


if __name__ == "__main__":
    main()
