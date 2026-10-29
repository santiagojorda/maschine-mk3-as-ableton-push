"""Protocolo entre los programas del proyecto: puertos UDP (todos en 127.0.0.1) y mensajes.

La fuente es contrato/protocolo.py. Hay dos copias idénticas porque cada programa solo importa de su carpeta:
Ableton/MaschineMK3AsPush/Protocolo.py (el script de Live) y Pantallas/prototipo/protocolo.py.
No se editan a mano: se edita la fuente y se corre  python tools/validar_contrato.py --arreglar
Qué lleva cada mensaje: contrato/PROTOCOLO.md
"""

# Campo "v" de cada JSON. Subirlo cuando un mensaje cambie de forma incompatible: el que recibe avisa en su
# registro si le llega otra versión (script y pantallas instalados de distintas ramas)
VERSION = 1
HOST = "127.0.0.1"

SCREENS_PORT = 9017  # script de Ableton -> pantallas: líneas MCU (sysex) y estado JSON
VDJ_REQUEST_PORT = 9018  # pantallas (vdj_data) -> vdj_puerto: REQUEST_ALL
VDJ_DATA_PORT = 9019  # vdj_puerto -> pantallas (vdj_data): cada sysex que manda VirtualDJ
SUPERVISOR_PORT = 9020  # cualquiera -> supervisor de las pantallas: QUIT / RESTART (también lo hace instancia única)
VDJ_TEMPO_PORT = 9021  # pantallas (vdj_master) -> script de Ableton: BPM del deck de referencia de VirtualDJ

# "type" de los JSON que el script manda a SCREENS_PORT
TYPE_STATE = "state"
TYPE_MODE = "mode"
TYPE_TEMPO = "tempo"
TYPE_TEMPO_FLASH = "tempo_flash"

# Órdenes de texto
QUIT = b"salir"
RESTART = b"reiniciar"
REQUEST_ALL = b"todo"

# Un solo dueño del modo: el script de Ableton decide (modo DJ, pads fijados con LOCK) y las pantallas se lo reenvían
# a VirtualDJ. A VDJ_REQUEST_PORT va VDJ_SYNC + 2 bytes (modo DJ 0/1, pads fijados 0/1); vdj_puerto.py lo pasa al
# puerto "MK3 Screens" como dos Control Change en el canal MIDI 1 (127 = sí), que el mapeo de ese puerto aplica
VDJ_SYNC = b"modo"
VDJ_SYNC_CC_DJ = 1
VDJ_SYNC_CC_LOCK = 2
