"""Los XML de VirtualDJ de la Maschine (VirtualDJ/Devices y Mappers) son lo que arma VirtualDJ/generar.py desde
VirtualDJ/fuente/. Si alguien edita un XML a mano, o una fuente sin volver a generar, esto falla."""

import sys
import unittest

from ayuda import RAIZ

sys.path.insert(0, str(RAIZ / "VirtualDJ"))
import generar  # noqa: E402


class XmlAlDia(unittest.TestCase):
    def test_los_xml_son_lo_que_sale_de_las_fuentes(self):
        dispositivo, mapeo, _ = generar.build()
        for ruta, esperado in ((generar.DEVICE, dispositivo), (generar.MAPPER, mapeo)):
            with self.subTest(ruta=ruta):
                with open(ruta, encoding="utf-8") as archivo:
                    self.assertEqual(archivo.read(), esperado,
                                     f"{ruta} no es lo que arma generar.py: corré python VirtualDJ/generar.py")


if __name__ == "__main__":
    unittest.main()
