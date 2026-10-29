"""Dibuja el ícono del ejecutable (prototipo\\icono.ico): una grilla de pads 4 x 4, como la de la Maschine."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
PAD_COLORS = [(255, 150, 30), (0, 170, 230), (235, 50, 70), (60, 200, 90)]


def main():
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, SIZE - 9, SIZE - 9), radius=44, fill=(24, 24, 24), outline=(70, 70, 70), width=4)
    gap, margin = 14, 38
    pad = (SIZE - 2 * margin - 3 * gap) // 4
    for row in range(4):
        for column in range(4):
            x = margin + column * (pad + gap)
            y = margin + row * (pad + gap)
            color = PAD_COLORS[(row + column) % 4] if (row * 4 + column) % 3 else (55, 55, 55)
            draw.rounded_rectangle((x, y, x + pad, y + pad), radius=10, fill=color)
    path = Path(__file__).with_name("icono.ico")
    image.save(path, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Ícono: {path}")


if __name__ == "__main__":
    main()
