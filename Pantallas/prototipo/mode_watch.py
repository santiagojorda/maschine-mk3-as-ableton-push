"""Paso 4: imprime DJ o ABLETON al apretar SAMPLING / MIXER / PLUGIN.

Uso:
  python mode_watch.py --list        lista los puertos MIDI de entrada
  python mode_watch.py [--port X]    escucha el puerto (por defecto "Maschine MK3 Ctrl MIDI")
  python mode_watch.py --all         además imprime todos los mensajes
"""

import argparse
import time

import mido

from mode import DEFAULT_PORT_HINT, ModeWatcher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=DEFAULT_PORT_HINT, help="parte del nombre del puerto MIDI")
    parser.add_argument("--list", action="store_true", help="listar puertos y salir")
    parser.add_argument("--all", action="store_true", help="imprimir todos los mensajes")
    args = parser.parse_args()

    if args.list:
        for name in mido.get_input_names():
            print(name)
        return

    watcher = ModeWatcher(
        port_hint=args.port,
        on_change=lambda mode: print(f"--> modo {mode.upper()}"),
        on_message=print if args.all else None,
    )
    print(f"Escuchando '{watcher.port_name}'. Apretá SAMPLING, MIXER o PLUGIN (Ctrl+C para salir).")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.close()


if __name__ == "__main__":
    main()
