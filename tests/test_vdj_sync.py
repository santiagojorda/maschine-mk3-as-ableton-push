"""Pantallas/prototipo/vdj_sync.py: cuándo le manda el modo a VirtualDJ (sin mandar nada de verdad: el socket es falso)."""

import sys
import unittest
from unittest import mock

from ayuda import RAIZ

sys.path.insert(0, str(RAIZ / "Pantallas" / "prototipo"))
import protocolo  # noqa: E402
import vdj_sync  # noqa: E402


class SocketFalso:
    def __init__(self):
        self.mandados = []

    def sendto(self, datos, direccion):
        self.mandados.append((datos, direccion))


class CuandoManda(unittest.TestCase):
    def setUp(self):
        self.reloj = 100.0
        parche = mock.patch.object(vdj_sync.time, "perf_counter", lambda: self.reloj)
        parche.start()
        self.addCleanup(parche.stop)
        self.sync = vdj_sync.VdjModeSync()
        self.sync._socket.close()
        self.sync._socket = SocketFalso()

    def mandados(self):
        return [datos[len(protocolo.VDJ_SYNC):] for datos, _ in self.sync._socket.mandados]

    def test_manda_el_modo_al_puerto_de_vdj_puerto(self):
        self.sync.maybe_send((True, False), last_button_time=0.0)
        datos, direccion = self.sync._socket.mandados[0]
        self.assertEqual(datos, protocolo.VDJ_SYNC + bytes((1, 0)))
        self.assertEqual(direccion, (protocolo.HOST, protocolo.VDJ_REQUEST_PORT))

    def test_sin_live_no_manda_nada(self):
        self.sync.maybe_send(None, last_button_time=0.0)
        self.assertEqual(self.mandados(), [])

    def test_justo_despues_de_un_boton_de_modo_espera(self):
        self.sync.maybe_send((False, False), last_button_time=self.reloj - 0.2)
        self.assertEqual(self.mandados(), [])
        self.reloj += 1.0
        self.sync.maybe_send((True, False), last_button_time=self.reloj - 1.2)
        self.assertEqual(self.mandados(), [bytes((1, 0))])

    def test_un_cambio_sale_enseguida_y_el_mismo_modo_cada_segundo(self):
        self.sync.maybe_send((False, False), last_button_time=0.0)
        self.reloj += 0.1
        self.sync.maybe_send((False, False), last_button_time=0.0)  # igual y hace poco: no
        self.sync.maybe_send((False, True), last_button_time=0.0)  # cambió: ya
        self.reloj += 1.1
        self.sync.maybe_send((False, True), last_button_time=0.0)  # igual, pero pasó un segundo
        self.assertEqual(self.mandados(), [bytes((0, 0)), bytes((0, 1)), bytes((0, 1))])


if __name__ == "__main__":
    unittest.main()
