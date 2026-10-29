"""Genera el dispositivo "MK3 Screens" de VirtualDJ: definición y mapeo.

VirtualDJ lo ve como un controlador más en el puerto virtual "MK3 Screens"
(lo crea el prototipo con teVirtualMIDI) y le manda el estado de cada deck por
sysex: F0 7D <campo> <texto ASCII> F7. Ver vdj_data.py para los campos.

Uso:
  python generar.py              genera los dos XML en esta carpeta y los valida
  python generar.py --instalar   además los copia a %LocalAppData%\\VirtualDJ
                                 (después hay que reiniciar VirtualDJ)
"""

import argparse
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

DEVICE_NAME = "MK3SCREENS"
PORT_NAME = "MK3 Screens"
HERE = Path(__file__).resolve().parent
DEVICE_FILE = HERE / "MK3-Screens.xml"
MAPPER_FILE = HERE / "MK3SCREENS - Datos pantallas.xml"

# (código del campo, nombre, largo del texto, acción para el deck n[, codificación])
# El título y el artista van dos veces: en ASCII (los acentos llegan como '?') y en UTF-8,
# por si el driver MIDI no deja pasar bytes de 8 bits dentro del sysex.
_SYNC = ("deck {n} masterdeck ? get_text 'M' : ((deck {n} match_bpm ? true : (deck {n} is_sync ? true : false))"
         " ? get_text 'S' : get_text '0')")
FIELDS = (
    (1, "TITLE", 60, "deck {n} get_title"),
    (2, "ARTIST", 40, "deck {n} get_artist"),
    (3, "BPM", 10, "deck {n} get_bpm & param_multiply 1000 & param_cast 'integer' & param_cast 'text' 10"),
    (4, "BPMORIG", 10, "deck {n} get_bpm absolute & param_multiply 1000 & param_cast 'integer' & param_cast 'text' 10"),
    (5, "PLAY", 1, "deck {n} play ? get_text '1' : get_text '0'"),
    (6, "VOL", 5, "deck {n} volume & param_multiply 1000 & param_cast 'integer' & param_cast 'text' 5"),
    (7, "FILTER", 5, "deck {n} filter & param_multiply 1000 & param_cast 'integer' & param_cast 'text' 5"),
    (8, "SYNC", 1, _SYNC),
    # El candado de VirtualDJ (pitch_lock), el del pad PITCH LOCK. No key_lock: el mapeo lo prende siempre
    (9, "PITCHLOCK", 1, "deck {n} pitch_lock ? get_text '1' : get_text '0'"),
    (10, "LOOP", 1, "deck {n} loop ? get_text '1' : get_text '0'"),
    # get_loop no se deja multiplicar: va el texto tal cual ("4", "0.5" o "1/2")
    (11, "LOOPLEN", 10, "deck {n} get_loop & param_cast 'text' 10"),
    (12, "TITLEU", 60, "deck {n} get_title", "utf8"),
    (13, "ARTISTU", 40, "deck {n} get_artist", "utf8"),
    (14, "LOADED", 1, "deck {n} loaded ? get_text '1' : get_text '0'"),
    # Cambia todo el tiempo mientras el deck suena: es el pulso que dice que VirtualDJ sigue conectado
    (15, "POS", 6, "deck {n} get_position & param_multiply 10000 & param_cast 'integer' & param_cast 'text' 6"),
)

# Campos generales, sin deck (campo = 0x30 + código). $encmode lo pone el mapeo de la Maschine:
# 1 = VOLUME (el encoder controla el master), 2 = SWING (auriculares), 3 = TEMPO (el tempo de Ableton)
GLOBAL_DECK = 3
GLOBAL_FIELDS = (
    (1, "ENCMODE", 1, "var '$encmode' 1 ? get_text '1' : (var '$encmode' 2 ? get_text '2' : (var '$encmode' 3 ? get_text '3' : get_text '0'))"),
    (2, "MASTERVOL", 5, "master_volume & param_multiply 1000 & param_cast 'integer' & param_cast 'text' 5"),
    (3, "HEADVOL", 5, "headphone_volume & param_multiply 1000 & param_cast 'integer' & param_cast 'text' 5"),
    (4, "CROSSFADER", 5, "crossfader & param_multiply 1000 & param_cast 'integer' & param_cast 'text' 5"),
)


def element_name(deck, name):
    return name if deck == GLOBAL_DECK else f"D{deck}_{name}"


def all_fields():
    """(deck, código, nombre, largo, acción, codificación) de cada salida."""
    for deck in (1, 2):
        for code, name, size, action, *encoding in FIELDS:
            yield deck, code, name, size, action.format(n=deck), (encoding or ["ascii"])[0]
    for code, name, size, action in GLOBAL_FIELDS:
        yield GLOBAL_DECK, code, name, size, action, "ascii"


def device_xml():
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!--",
        "  Datos para las pantallas de la Maschine MK3 (maschine-mk3-driver).",
        f'  Puerto virtual "{PORT_NAME}", creado por el prototipo. Generado por generar.py: no editar a mano.',
        "-->",
        f'<device name="{DEVICE_NAME}" author="Santiago Jorda" description="Pantallas Maschine MK3 (datos)" '
        f'version="800" type="MIDI" decks="2" drivername="{PORT_NAME}" drivernameout="{PORT_NAME}">',
    ]
    for deck, code, name, size, _, encoding in all_fields():
        field = (deck << 4) | code
        sysex = f"F07D{field:02X}" + "20" * size + "F7"
        deck_attribute = "" if deck == GLOBAL_DECK else f' deck="{deck}"'
        lines.append(
            f'  <text sysex="{sysex}" offset="3" size="{size}" encoding="{encoding}" scroll="false" '
            f'name="{element_name(deck, name)}"{deck_attribute} />'
        )
    lines.append("</device>")
    return "\n".join(lines) + "\n"


def mapper_xml():
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<mapper device="{DEVICE_NAME}" author="Santiago Jorda" version="800" date="2026-10-08">',
    ]
    for deck, _, name, _, action, _ in all_fields():
        escaped = action.replace("&", "&amp;")
        lines.append(f'  <map value="{element_name(deck, name)}" action="{escaped}" />')
    lines.append("</mapper>")
    return "\n".join(lines) + "\n"


def validate():
    device = ET.parse(DEVICE_FILE).getroot()
    mapper = ET.parse(MAPPER_FILE).getroot()
    names = {element.get("name") for element in device}
    for entry in mapper.iter("map"):
        if entry.get("value") not in names:
            raise SystemExit(f"El mapeo usa '{entry.get('value')}', que no está en la definición")
    print(f"OK: {len(names)} salidas definidas y mapeadas")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instalar", action="store_true", help="copiar a la carpeta de VirtualDJ")
    args = parser.parse_args()

    DEVICE_FILE.write_text(device_xml(), encoding="utf-8")
    MAPPER_FILE.write_text(mapper_xml(), encoding="utf-8")
    validate()

    if args.instalar:
        vdj = Path(os.environ["LOCALAPPDATA"]) / "VirtualDJ"
        shutil.copy2(DEVICE_FILE, vdj / "Devices" / DEVICE_FILE.name)
        shutil.copy2(MAPPER_FILE, vdj / "Mappers" / MAPPER_FILE.name)
        print(f"Instalado en {vdj}. Reiniciá VirtualDJ para que lo tome.")


if __name__ == "__main__":
    main()
