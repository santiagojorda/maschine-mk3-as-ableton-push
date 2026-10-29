"""MidiRouter.py hace exactamente lo mismo que el _accept_midi y el filtro de _do_send_midi de antes de la fase 3.

El código viejo se saca de git (REF), se corre con un Live de mentira que anota cada efecto, y se compara con el router
nuevo sobre secuencias de mensajes al azar (con semilla fija, así un fallo se repite): lo que pasa a Ableton, los
efectos en orden y el estado después de cada mensaje.

Es la red de seguridad de la migración. Cuando el router cambie de comportamiento a propósito (fase 4), este test
deja de servir y se borra; los de test_escenarios.py quedan.
"""

import ast
import contextlib
import random
import subprocess
import unittest

from ayuda import RAIZ, Entorno, cargar_router

REF = "6e70aed"  # main antes de la fase 3
ESTADO = ("standby", "vdj_mode", "pad_lock", "shift_down", "scene_down", "restart_held", "restart_used", "follow_held",
          "follow_used", "swallow_lock_release", "swallow_tempo_release", "erase_touch")
SHIFT_MK3 = (0xF0, 0x00, 0x21, 0x09, 0x16, 0x00, 0x4D, 0x50, 0x00, 0x01, 0x4D)
EFECTOS_SIMPLES = ("_launch_cursor_scene", "_capture_scene", "_turn_tempo", "_sync_tempo_with_virtualdj",
                   "_restart_screens", "_clear_prelisten", "_reset_all_volumes", "_stop_knob_track_clip",
                   "_toggle_knob_track_prelisten", "_launch_knob_track_clip", "_handle_session_navigation",
                   "_new_scene_below_cursor", "_delete_clip", "_show_session_view")


class _SuperASelf(ast.NodeTransformer):
    """super()._do_send_midi(x) -> self._sent(x): la función se compila fuera de su clase."""

    def visit_Call(self, nodo):
        self.generic_visit(nodo)
        funcion = nodo.func
        if (isinstance(funcion, ast.Attribute) and funcion.attr == "_do_send_midi"
                and isinstance(funcion.value, ast.Call) and getattr(funcion.value.func, "id", None) == "super"):
            nodo.func = ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="_sent", ctx=ast.Load())
        return nodo


def codigo_viejo(reloj):
    fuente = subprocess.run(["git", "-C", str(RAIZ), "show", f"{REF}:Ableton/CustomMaschineMK3/CustomMaschineMK3.py"],
                            capture_output=True, check=True).stdout.decode("utf-8")
    arbol = ast.parse(fuente)
    globales = {"__builtins__": __builtins__, "perf_counter": reloj, "sleep": lambda segundos: None,
                "logger": type("L", (), {"debug": staticmethod(lambda *a: None)})()}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name) and nodo.targets[0].id.isupper():
            try:
                globales[nodo.targets[0].id] = eval(compile(ast.Expression(nodo.value), "<c>", "eval"), dict(globales))
            except Exception:
                pass  # las que usan Live, Config o Protocolo: el ruteo no las usa
    clase = next(n for n in arbol.body if isinstance(n, ast.ClassDef) and n.name == "CustomMaschineMK3")
    funciones = [n for n in clase.body if isinstance(n, ast.FunctionDef)
                 and n.name in ("_accept_midi", "_is_vdj_only", "_is_pad_section", "_do_send_midi")]
    for funcion in funciones:
        funcion.decorator_list = []
    modulo = ast.fix_missing_locations(_SuperASelf().visit(ast.Module(body=funciones, type_ignores=[])))
    exec(compile(modulo, f"{REF}:CustomMaschineMK3.py", "exec"), globales)
    return globales


class LiveViejo:
    """El self que espera el código viejo: anota cada efecto como (nombre del efecto nuevo, *args)."""

    def __init__(self, viejo, standby, entorno, anotados):
        self._viejo, self._entorno, self._anotados = viejo, entorno, anotados
        self._standby, self._vdj_mode, self._pad_lock = standby, False, False
        self._shift_down = self._scene_down = False
        self._restart_held = self._restart_used = self._follow_held = self._follow_used = False
        self._swallow_lock_release = self._swallow_tempo_release = False
        self._erase_touch = (None, 0.0)
        self._loop = False
        anotar = anotados.append
        boton = lambda atributo: type("B", (), {"is_pressed": property(lambda s: getattr(entorno, atributo))})()
        self.elements = type("E", (), {})()
        for nombre in ("shift", "solo", "erase", "mute", "macro", "plugin"):
            setattr(self.elements, nombre, boton(f"{nombre}_pressed"))
        self._c_instance = type("C", (), {"log_message": staticmethod(
            lambda texto: anotar(("_log", texto.replace("CustomMaschineMK3: ", "", 1))))})()
        componentes = {
            "Display_Modes": property(lambda s: type("M", (), {"selected_mode": entorno.display_mode})()),
            "Encoder_Modes": property(lambda s: type("M", (), {"selected_mode": entorno.encoder_mode})()),
        }
        control = type("EMC", (), {"reset_selected_mode": staticmethod(lambda: anotar(("_reset_encoder_mode",)))})()
        notas = type("GBMC", (), {
            "get_note_repeat_selector_state": staticmethod(lambda: entorno.note_repeat_open),
            "set_note_repeat_selector_state": staticmethod(
                lambda valor: anotar(("_close_note_repeat_selector",)) if not valor else None)})()
        self.component_map = _Componentes(entorno, control, notas)
        self.song = self
        for nombre in EFECTOS_SIMPLES:
            setattr(self, nombre, (lambda n: lambda *args: anotar((n, *args)))(nombre))
        self.sent = []

    # lo que el código viejo llama de self
    _is_vdj_only = property(lambda self: self._viejo["_is_vdj_only"])
    _is_pad_section = property(lambda self: self._viejo["_is_pad_section"])
    _session_view = property(lambda self: self._entorno.display_mode == "session")

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, valor):
        self._loop = valor
        self._anotados.append(("_toggle_loop",))

    def component_guard(self):
        return contextlib.nullcontext()

    def _log(self, texto):
        self._anotados.append(("_log", texto))

    def _encoder_tempo_mode(self):
        return self._entorno.encoder_tempo_mode

    def _set_standby(self, enabled):
        if enabled == self._standby:
            return
        if enabled:
            self._vdj_mode = self._pad_lock = False
        self._standby = enabled
        self._anotados.append(("_on_standby_changed", enabled))

    def _set_vdj_mode(self, enabled):
        self._vdj_mode = enabled
        self._anotados.append(("_on_vdj_mode_changed", enabled))

    def _set_pad_lock(self, enabled):
        self._pad_lock = enabled
        self._anotados.append(("_on_pad_lock_changed", enabled))

    def _set_knob_parameter(self, index, default):
        self._anotados.append(("_set_knob_parameter", index, default))

    def _sent(self, mensaje):
        self.sent.append(mensaje)

    def _copy_to_screen_bridge(self, mensaje):
        pass

    def estado(self):
        return tuple(getattr(self, "_" + nombre) for nombre in ESTADO)


class _Componentes:
    def __init__(self, entorno, control, notas):
        self._entorno, self._control, self._notas = entorno, control, notas

    def __getitem__(self, nombre):
        if nombre == "Display_Modes":
            return type("M", (), {"selected_mode": self._entorno.display_mode})()
        if nombre == "Encoder_Modes":
            return type("M", (), {"selected_mode": self._entorno.encoder_mode})()
        if nombre == "Encoder_Mode_Control":
            return self._control
        if nombre == "Group_Button_Mode_Control":
            return self._notas
        raise KeyError(nombre)


def mensaje_al_azar(azar):
    tipo = azar.random()
    if tipo < 0.55:  # botones del canal 2: los que más reglas tienen
        cc = azar.choice([7, 7, 8, 9, *range(10, 18), *range(30, 60), 64, 65, *range(80, 93), *range(100, 108),
                          110, 111, 119, azar.randrange(128)])
        valor = azar.choice([1, 127, 65]) if cc == 7 else azar.choice([0, 127, 127])
        return (0xB1, cc, valor)
    if tipo < 0.62:
        return (0xB0, azar.randrange(16, 24), azar.choice([1, 65]))  # perillas
    if tipo < 0.80:
        estado = azar.choice([0x90, 0x80, 0xA0, 0x91, 0x81, 0xA1])
        return (estado, azar.choice([*range(60, 76), *range(0, 8), azar.randrange(128)]), azar.choice([0, 100]))
    if tipo < 0.88:
        return (azar.choice([0xE0, 0xE1]), azar.randrange(128), azar.randrange(128))
    if tipo < 0.96:
        return SHIFT_MK3 + (azar.choice([0, 1]), 0xF7)
    return (0xF0, 0x00, 0x00, 0x66, 0x17, 0x12, azar.randrange(112), 0x20, 0xF7)  # otro sysex


BOTONES_DEL_ENTORNO = ("shift_pressed", "solo_pressed", "erase_pressed", "mute_pressed", "macro_pressed",
                       "plugin_pressed", "encoder_tempo_mode", "note_repeat_open")


def mover_entorno(azar, entorno):
    """Cambia de a poco, como en la Maschine: un modificador queda apretado varios mensajes seguidos."""
    for nombre in BOTONES_DEL_ENTORNO:
        if azar.random() < 0.12:
            setattr(entorno, nombre, not getattr(entorno, nombre))
    if azar.random() < 0.1:
        entorno.display_mode = azar.choice(["default", "default", "session", "device", "browser"])
    if azar.random() < 0.1:
        entorno.encoder_mode = azar.choice(["default", "default", "tempo", "volume"])


class EquivalenciaConElCodigoViejo(unittest.TestCase):
    SECUENCIAS = 1500
    LARGO = 60

    @classmethod
    def setUpClass(cls):
        cls.reloj = [0.0]
        try:
            cls.viejo = codigo_viejo(lambda: cls.reloj[0])
        except (subprocess.CalledProcessError, FileNotFoundError) as error:
            raise unittest.SkipTest(f"no se pudo leer {REF} de git: {error}")
        cls.router = cargar_router()

    def test_entrada_igual_mensaje_por_mensaje(self):
        azar = random.Random(20261029)
        for secuencia in range(self.SECUENCIAS):
            # Cada secuencia arranca en un modo al azar: llegar al pad lock apretando botones al azar es muy raro
            standby = azar.random() < 0.25
            vdj_mode, pad_lock = azar.random() < 0.35, azar.random() < 0.35
            entorno = Entorno()
            anotados_viejo, anotados_nuevo = [], []
            viejo = LiveViejo(self.viejo, standby, entorno, anotados_viejo)
            viejo._vdj_mode, viejo._pad_lock = vdj_mode, pad_lock
            nuevo = self.router.MidiRouter(standby=standby, clock=lambda: self.reloj[0])
            nuevo.vdj_mode, nuevo.pad_lock = vdj_mode, pad_lock

            def correr(nombre, *args):
                if nombre == "_close_note_repeat_selector" and not entorno.note_repeat_open:
                    return  # el script solo lo cierra si está abierto, como hacía el código viejo
                anotados_nuevo.append((nombre, *args))

            historia = []
            for paso in range(self.LARGO):
                mover_entorno(azar, entorno)
                # Saltos a los dos lados de los límites de tiempo (el doble toque de ERASE es 0,4 s)
                self.reloj[0] += azar.choice([0.05, 0.15, 0.3, 0.39, 0.41, 0.6])
                # A veces el mismo mensaje otra vez: dobles toques, apretar y soltar seguidos
                mensaje = historia[-1] if historia and azar.random() < 0.2 else mensaje_al_azar(azar)
                historia.append(mensaje)
                del anotados_viejo[:], anotados_nuevo[:]
                pasa_viejo = self.viejo["_accept_midi"](viejo, mensaje)
                pasa_nuevo = nuevo.accept(mensaje, entorno, correr)
                contexto = f"secuencia {secuencia}, paso {paso}, mensaje {mensaje}, historia {historia[-6:]}"
                self.assertEqual(bool(pasa_viejo), bool(pasa_nuevo), f"pasa a Ableton: {contexto}")
                self.assertEqual(anotados_viejo, anotados_nuevo, f"efectos: {contexto}")
                self.assertEqual(viejo.estado(), tuple(getattr(nuevo, n) for n in ESTADO), f"estado: {contexto}")

    def test_salida_igual(self):
        azar = random.Random(7)
        for _ in range(20000):
            estado = dict(standby=azar.random() < 0.3, vdj_mode=azar.random() < 0.4, pad_lock=azar.random() < 0.4)
            viejo = LiveViejo(self.viejo, estado["standby"], Entorno(), [])
            viejo._vdj_mode, viejo._pad_lock = estado["vdj_mode"], estado["pad_lock"]
            nuevo = self.router.MidiRouter()
            for nombre, valor in estado.items():
                setattr(nuevo, nombre, valor)
            mensaje = mensaje_al_azar(azar)
            self.viejo["_do_send_midi"](viejo, mensaje)
            self.assertEqual(bool(viejo.sent), nuevo.lets_out(mensaje), f"{estado} {mensaje}")


if __name__ == "__main__":
    unittest.main()
