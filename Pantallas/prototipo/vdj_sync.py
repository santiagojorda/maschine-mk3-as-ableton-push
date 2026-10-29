"""Le dice a VirtualDJ en qué modo está la Maschine, según el script de Ableton (el dueño del modo).

Sin esto, el script y el mapeo de VirtualDJ deducían el modo cada uno por su lado, mirando los mismos botones, y se
desincronizaban si uno de los dos se reiniciaba: con Live reiniciado en modo DJ respondían los dos a la vez, y con
VirtualDJ reiniciado no respondía ninguno (ANALISIS-ACOPLAMIENTO.md, 3.1 y 3.2).

Cada segundo, y apenas cambia, manda (modo DJ, pads fijados) a vdj_puerto.py, que lo pasa al puerto "MK3 Screens";
el mapeo de ese puerto (vdj/generar.py) corrige $vdj, $padlock y $pads solo si no coinciden. Si el script no avisa
(Live cerrado), no manda nada y VirtualDJ sigue solo. Justo después de un botón de modo espera: los dos programas
lo están procesando y el script puede tardar un instante en informarlo.
"""

import logging
import socket
import time

import protocolo

log = logging.getLogger("vdj_sync")

RESEND_SECONDS = 1.0
QUIET_AFTER_BUTTON = 1.0


class VdjModeSync:
    def __init__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._last = None
        self._last_time = 0.0

    def maybe_send(self, routing, last_button_time):
        """routing: (modo DJ, pads fijados) de AbletonText.routing(), o None. last_button_time: perf_counter del
        último botón de modo (ModeWatcher.last_button_time)."""
        now = time.perf_counter()
        if routing is None or now - last_button_time < QUIET_AFTER_BUTTON:
            return
        if routing == self._last and now - self._last_time < RESEND_SECONDS:
            return
        if routing != self._last:
            log.info(f"Modo de Ableton para VirtualDJ: DJ {routing[0]}, pads fijados {routing[1]}")
        self._last, self._last_time = routing, now
        try:
            self._socket.sendto(protocolo.VDJ_SYNC + bytes((int(routing[0]), int(routing[1]))),
                                (protocolo.HOST, protocolo.VDJ_REQUEST_PORT))
        except OSError:
            pass  # vdj_puerto.py no está corriendo: el supervisor lo vuelve a lanzar

    def close(self):
        self._socket.close()
