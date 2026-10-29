"""Escenarios con los dos programas a la vez: cada control le llega al router de Ableton (MidiRouter.py) y al mapeo de
VirtualDJ de verdad (VirtualDJ/Mappers, interpretado con tools/vdjscript.py), como en la Maschine.

Cada paso dice quién reaccionó: Ableton (dejó pasar el mensaje a Live, cambió de modo o hizo algo que se ve o se
oye) y VirtualDJ (lo que haría: deck, crossfader...). Lo que VirtualDJ pregunta a un deck o al browser se toma como
falso, y un <button> de VirtualDJ corre su acción al apretarlo (un <slider>, también al soltarlo).

Las pantallas le reenvían a VirtualDJ el modo que decide el script (Pantallas/prototipo/vdj_sync.py, por el puerto
"MK3 Screens", con el mapeo de Pantallas/prototipo/vdj): la simulación lo hace después de cada paso, como si pasara un
segundo, mientras Live esté abierto. Así no se desincronizan aunque uno de los dos se reinicie
(ANALISIS-ACOPLAMIENTO.md, 3.1 y 3.2).
"""

import unittest
import xml.etree.ElementTree as ET

from ayuda import RAIZ, Entorno, cargar_router
from contrato.controles import POR_NOMBRE
import vdjscript

DEVICE = RAIZ / "VirtualDJ" / "Devices" / "MaschineMK3-VDJ.xml"
MAPPER = RAIZ / "VirtualDJ" / "Mappers" / "MASCHINEMK3VDJ - Mapeo Personalizado.xml"
MAPPER_DATOS = RAIZ / "Pantallas" / "prototipo" / "vdj" / "MK3SCREENS - Datos pantallas.xml"
SHIFT_MK3 = (0xF0, 0x00, 0x21, 0x09, 0x16, 0x00, 0x4D, 0x50, 0x00, 0x01, 0x4D)

ROUTER = cargar_router()
TIPO_EN_VDJ = {e.get("name"): e.tag for e in ET.parse(DEVICE).getroot()}
ACCIONES_VDJ = {m.get("value"): vdjscript.analizar(m.get("action")) for m in ET.parse(MAPPER).getroot() if m.tag == "map"}
# Las entradas del puerto "MK3 Screens" (el modo que decide el script) comparten las variables $ con el mapeo
ACCIONES_VDJ.update({m.get("value"): vdjscript.analizar(m.get("action"))
                     for m in ET.parse(MAPPER_DATOS).getroot() if m.get("value", "").startswith("ABLETON_")})


class Respuesta:
    def __init__(self, ableton, vdj):
        self.ableton, self.vdj = ableton, vdj

    def __repr__(self):
        return f"Ableton {'reacciona' if self.ableton else 'no'}, VirtualDJ {self.vdj or 'no'}"


class Maschine:
    """La Maschine conectada a Live (con el script) y a VirtualDJ al mismo tiempo."""

    def __init__(self, ableton_en_reposo=False):
        self.vdj = {}
        self.reiniciar_live(ableton_en_reposo)
        self.reiniciar_vdj()

    def reiniciar_live(self, en_reposo=True):
        # El script arranca en reposo (Config.START_IN_STANDBY) y con todo el estado de ruteo en cero
        self.ableton = ROUTER.MidiRouter(standby=en_reposo, clock=lambda: 0.0)
        self.sincronizar()

    def cerrar_live(self):
        self.ableton = None

    def reiniciar_vdj(self):
        self.vdj.clear()
        vdjscript.ejecutar(ACCIONES_VDJ["ONINIT"], self.vdj)
        self.sincronizar()

    def sincronizar(self):
        """Lo que hacen vdj_sync.py y vdj_puerto.py cada segundo: el modo del script, a VirtualDJ (pads fijados
        primero). Con Live cerrado no se manda nada."""
        if self.ableton is None:
            return
        dj, fijados = self.ableton.vdj_mode, self.ableton.pad_lock and not self.ableton.standby
        self._a_vdj("ABLETON_LOCK", 1.0 if fijados else 0.0)
        self._a_vdj("ABLETON_DJ", 1.0 if dj else 0.0)

    def _a_ableton(self, mensaje):
        if self.ableton is None:
            return False
        antes = (self.ableton.standby, self.ableton.vdj_mode, self.ableton.pad_lock)
        efectos = []
        pasa = self.ableton.accept(mensaje, Entorno(), lambda nombre, *a: efectos.append(nombre))
        cambio = antes != (self.ableton.standby, self.ableton.vdj_mode, self.ableton.pad_lock)
        return bool(pasa or cambio or any(e not in ROUTER.STATE_ONLY_EFFECTS for e in efectos))

    def _a_vdj(self, nombre, valor):
        if nombre not in ACCIONES_VDJ:
            return []
        return vdjscript.ejecutar(ACCIONES_VDJ[nombre], self.vdj, valor)

    def apretar(self, nombre):
        """Apretar y soltar un control del contrato (contrato/controles.py)."""
        control = POR_NOMBRE[nombre]
        canal, mensaje = control.canal - 1, None
        estado = (0x90 if control.tipo == "nota" else 0xB0) | canal
        ableton = self._a_ableton((estado, control.numero, 127))
        vdj = self._a_vdj(control.vdj, 1.0)
        ableton = self._a_ableton((estado, control.numero, 0)) or ableton
        if TIPO_EN_VDJ.get(control.vdj) == "slider":
            vdj += self._a_vdj(control.vdj, 0.0)
        self.sincronizar()
        return Respuesta(ableton, vdj)

    def girar(self, nombre):
        """Girar una perilla un paso a la derecha."""
        control = POR_NOMBRE[nombre]
        respuesta = Respuesta(self._a_ableton((0xB0 | (control.canal - 1), control.numero, 1)),
                              self._a_vdj(control.vdj, 1.0))
        self.sincronizar()
        return respuesta

    def shift(self, apretado):
        # El MK3 manda SHIFT por sysex: lo leen los dos
        self._a_ableton(SHIFT_MK3 + (1 if apretado else 0, 0xF7))
        self._a_vdj("SHIFT_ON" if apretado else "SHIFT_OFF", 1.0)

    @property
    def vdj_en_modo_dj(self):
        return self.vdj.get("$vdj", 0) != 0


class CambiosDeModo(unittest.TestCase):
    def test_sampling_pasa_los_dos_a_modo_dj(self):
        m = Maschine()
        m.apretar("SAMPLING")
        self.assertTrue(m.ableton.vdj_mode)
        self.assertTrue(m.vdj_en_modo_dj)

    def test_en_modo_ableton_la_perilla_es_solo_de_ableton(self):
        r = Maschine().girar("KNOB1")
        self.assertTrue(r.ableton, r)
        self.assertEqual(r.vdj, [], r)

    def test_en_modo_dj_la_perilla_es_solo_de_virtualdj(self):
        m = Maschine()
        m.apretar("SAMPLING")
        r = m.girar("KNOB1")
        self.assertFalse(r.ableton, r)
        self.assertTrue(r.vdj, r)

    def test_mixer_vuelve_los_dos_a_ableton(self):
        m = Maschine()
        m.apretar("SAMPLING")
        m.apretar("MIXER")
        self.assertFalse(m.ableton.vdj_mode)
        self.assertFalse(m.vdj_en_modo_dj)
        r = m.girar("KNOB1")
        self.assertTrue(r.ableton and not r.vdj, r)

    def test_play_sigue_siendo_de_ableton_en_modo_dj(self):
        m = Maschine()
        m.apretar("SAMPLING")
        r = m.apretar("PLAY")
        self.assertTrue(r.ableton, r)
        self.assertEqual(r.vdj, [], r)

    def test_shift_channel_pasa_los_dos_a_reposo(self):
        m = Maschine()
        m.apretar("SAMPLING")
        m.shift(True)
        m.apretar("CHANNEL")
        m.shift(False)
        self.assertTrue(m.ableton.standby)
        self.assertFalse(m.vdj_en_modo_dj)

    def test_channel_despierta_a_ableton(self):
        m = Maschine(ableton_en_reposo=True)
        m.apretar("CHANNEL")
        self.assertFalse(m.ableton.standby)
        self.assertTrue(m.girar("KNOB1").ableton)


class PadLock(unittest.TestCase):
    def test_lock_deja_los_pads_en_virtualdj_y_lock_los_devuelve(self):
        m = Maschine()
        m.apretar("SAMPLING")
        m.apretar("LOCK")
        m.apretar("MIXER")
        self.assertTrue(m.ableton.pad_lock)
        self.assertFalse(m.ableton.vdj_mode)
        r = m.apretar("PAD13")  # hot cue 1 del deck 1
        self.assertFalse(r.ableton, r)
        self.assertTrue(r.vdj, r)
        r = m.girar("KNOB1")  # las perillas no quedan fijadas: son de Ableton
        self.assertTrue(r.ableton and not r.vdj, r)
        m.apretar("LOCK")
        self.assertFalse(m.ableton.pad_lock)
        r = m.apretar("PAD13")
        self.assertTrue(r.ableton and not r.vdj, r)


class Desincronizaciones(unittest.TestCase):
    """ANALISIS-ACOPLAMIENTO.md, secciones 3.1 y 3.2: el script es el dueño del modo y VirtualDJ lo sigue."""

    def test_live_reiniciado_en_modo_dj_no_deja_a_los_dos_respondiendo(self):
        m = Maschine()
        m.apretar("SAMPLING")
        m.reiniciar_live()  # Live arranca en reposo; VirtualDJ sigue en modo DJ
        m.apretar("CHANNEL")  # despierta a Ableton en modo Ableton
        r = m.girar("KNOB1")
        self.assertFalse(r.ableton and r.vdj, f"responden los dos: {r}")
        self.assertFalse(m.vdj_en_modo_dj)

    def test_virtualdj_reiniciado_en_modo_dj_no_deja_la_maschine_muerta(self):
        m = Maschine()
        m.apretar("SAMPLING")
        m.reiniciar_vdj()  # VirtualDJ arranca fuera del modo DJ; Ableton sigue en modo DJ
        r = m.girar("KNOB1")
        self.assertTrue(r.ableton or r.vdj, f"no responde nadie: {r}")
        self.assertTrue(r.vdj and not r.ableton, r)

    def test_virtualdj_reiniciado_con_lock_recupera_los_pads(self):
        m = Maschine()
        m.apretar("SAMPLING")
        m.apretar("LOCK")
        m.apretar("MIXER")
        m.reiniciar_vdj()
        r = m.apretar("PAD13")
        self.assertTrue(r.vdj and not r.ableton, r)

    def test_sin_live_virtualdj_funciona_solo(self):
        m = Maschine()
        m.cerrar_live()
        m.reiniciar_vdj()
        m.apretar("SAMPLING")
        self.assertTrue(m.vdj_en_modo_dj)
        self.assertTrue(m.girar("KNOB1").vdj)
        m.apretar("MIXER")
        self.assertFalse(m.vdj_en_modo_dj)


if __name__ == "__main__":
    unittest.main()
