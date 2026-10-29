"""Punto de entrada del ejecutable: MaschineMK3AsPush.exe

  (sin opciones)    arranca el supervisor: las pantallas y el puerto de datos de VirtualDJ, siempre vivos
  --salir           detiene el supervisor y las pantallas
  --instalar-vdj    instala en VirtualDJ el dispositivo de datos de las pantallas (reiniciar VirtualDJ después)
  --screens, --port procesos internos que lanza el supervisor

Suelto, con Python, equivale a prototipo\\supervisor.py.
"""

import os
import shutil
import socket
import sys

from paths import BUNDLE_DIR, FROZEN, message_box


def _fix_stdio():
    # Sin consola, stdout / stderr pueden no existir; con la salida a un pipe, que no se pierdan líneas
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
        else:
            try:
                stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            except (AttributeError, ValueError):
                pass


def _stop():
    from supervisor import SINGLE_INSTANCE_ADDRESS
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(b"salir", SINGLE_INSTANCE_ADDRESS)
    sock.close()
    message_box("Pantallas detenidas.")


def _install_vdj():
    folder = os.path.join(os.environ["LOCALAPPDATA"], "VirtualDJ")
    source = BUNDLE_DIR / "vdj"
    shutil.copy2(source / "MK3-Screens.xml", os.path.join(folder, "Devices", "MK3-Screens.xml"))
    shutil.copy2(source / "MK3SCREENS - Datos pantallas.xml",
                 os.path.join(folder, "Mappers", "MK3SCREENS - Datos pantallas.xml"))
    message_box("Instalado en VirtualDJ. Reinicialo para que lo tome.")


def main():
    _fix_stdio()
    option = sys.argv[1] if len(sys.argv) > 1 else ""
    if option == "--screens":
        import dj_screens
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return dj_screens.main()
    if option == "--port":
        import vdj_puerto
        return vdj_puerto.main()
    if option == "--salir":
        return _stop()
    if option == "--instalar-vdj":
        return _install_vdj()
    import supervisor
    result = supervisor.main()
    if result == supervisor.ALREADY_RUNNING and FROZEN:
        message_box("Las pantallas ya están funcionando.\n\nPara detenerlas: MaschineMK3AsPush.exe --salir")
    return 0 if result == supervisor.ALREADY_RUNNING else result


if __name__ == "__main__":
    sys.exit(main() or 0)
