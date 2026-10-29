"""Registro de las pantallas: una línea por evento, con fecha, nivel y quién la dice; los errores, con su detalle.

- Las pantallas escriben a la salida estándar; el supervisor la guarda en pantallas.log (con rotación).
- El puerto de datos de VirtualDJ (vdj_puerto.py) corre aparte y escribe en su propio archivo (vdj_puerto.log).
- Un error que nadie atrapó (en el programa o en un hilo) también queda registrado, con su detalle.
"""

import faulthandler
import logging
import logging.handlers
import sys
import threading

FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
FECHA = "%Y-%m-%d %H:%M:%S"


def configurar(archivo=None, nivel=logging.INFO):
    """Prepara el registro. Sin archivo, a la salida estándar; con archivo, a ese archivo (rota a los 2 MB)."""
    raiz = logging.getLogger()
    if getattr(raiz, "_mk3_configurado", False):
        return
    raiz._mk3_configurado = True
    raiz.setLevel(nivel)
    if archivo is not None:
        manejador = logging.handlers.RotatingFileHandler(archivo, maxBytes=2 * 1024 * 1024, backupCount=3,
                                                         encoding="utf-8")
    else:
        manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(logging.Formatter(FORMATO, FECHA))
    raiz.addHandler(manejador)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    def sin_atrapar(tipo, valor, traza):
        logging.getLogger("fatal").critical("Error sin atrapar", exc_info=(tipo, valor, traza))

    def sin_atrapar_en_hilo(datos):
        logging.getLogger("hilo").critical(f"Error sin atrapar en el hilo {datos.thread.name if datos.thread else '?'}",
                                           exc_info=(datos.exc_type, datos.exc_value, datos.exc_traceback))

    sys.excepthook = sin_atrapar
    threading.excepthook = sin_atrapar_en_hilo
    try:
        faulthandler.enable()  # si Python mismo se cae, queda el motivo en la salida de error
    except Exception:
        pass
