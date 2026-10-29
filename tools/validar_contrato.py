"""Compara contrato/controles.py con lo que está escrito a mano en cada programa y busca controles con dos dueños.

Qué revisa:
  1. VirtualDJ/Devices/MaschineMK3-VDJ.xml: cada control con el mismo número, canal y nombre que el contrato.
  2. Ableton/MaschineMK3AsPush/ControlElements.py: lo mismo con los elementos del script.
  3. El script de Ableton: que cada (0xB1, n) de sus constantes sea un control del contrato, y que los dueños
     del contrato coincidan con lo que hace MidiRouter.py (el ruteo de verdad) en cada modo.
  4. Pantallas/prototipo/mode.py: los botones que cambian el modo.
  5. El mapeo de VirtualDJ: evalúa cada acción en cada modo ($vdj, $pads, $padlock) y avisa si VirtualDJ hace algo
     con un control que el contrato le da solo a Ableton, o si prende una luz que Ableton también maneja.
  6. contrato/protocolo.py: que sus dos copias (script y pantallas) sean iguales y que ningún archivo tenga un
     puerto UDP escrito a mano.

Uso:  python tools/validar_contrato.py            errores y avisos
      python tools/validar_contrato.py --tabla    además, la tabla de dueños por modo
      python tools/validar_contrato.py --todo     además, lo informativo (seguimiento "de oído", controles libres)
      python tools/validar_contrato.py --arreglar vuelve a copiar contrato/protocolo.py a sus dos copias
Sale con código 1 si hay errores.
"""

import argparse
import ast
import importlib.util
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from contrato.controles import CONTROLES, DUENOS, MODOS, PANTALLA_COMPARTIDA, POR_NOMBRE  # noqa: E402
from vdjscript import Analizador, acciones, condicion  # noqa: E402

DEVICE = RAIZ / "VirtualDJ" / "Devices" / "MaschineMK3-VDJ.xml"
MAPPER = RAIZ / "VirtualDJ" / "Mappers" / "MASCHINEMK3VDJ - Mapeo Personalizado.xml"
SCRIPT = RAIZ / "Ableton" / "MaschineMK3AsPush"
MODE_PY = (RAIZ / "Pantallas" / "prototipo" / "mode.py",)
# El script de Ableton: la clase principal y los mixins en que está partida
MODULOS_SCRIPT = ("MaschineMK3AsPush.py", "ScreenBridge.py", "SessionNavigation.py", "KnobActions.py")

# Variables del mapeo de VirtualDJ en cada modo de la Maschine (las demás quedan "desconocidas": se miran las dos ramas)
ENTORNO_VDJ = {
    "ableton": {"$vdj": 0, "$pads": 0, "$padlock": 0, "$select": 0},
    "lock": {"$vdj": 0, "$pads": 1, "$padlock": 1, "$select": 0},
    "dj": {"$vdj": 1, "$pads": 1, "$select": 0},
    "reposo": {"$vdj": 0, "$pads": 0, "$padlock": 0, "$select": 0},
}
# Verbos de VirtualDJ que solo leen o anotan variables: no se oyen ni se ven
SOLO_ESTADO = {"set", "toggle", "nothing", "repeat_start", "repeat_stop", "var", "true", "false", "get_text",
               "param_bigger", "param_smaller", "param_greater", "var_smaller", "var_greater", "param_cast"}
ALIAS_VDJ = {"SHIFT_ON": "SHIFT", "SHIFT_OFF": "SHIFT"}


class Informe:
    def __init__(self):
        self.errores, self.avisos, self.info = [], [], []

    def error(self, texto):
        self.errores.append(texto)

    def aviso(self, texto):
        self.avisos.append(texto)

    def nota(self, texto):
        self.info.append(texto)


def direccion(control):
    return (control.tipo, control.numero, control.canal)


def nombre_direccion(clave):
    tipo, numero, canal = clave
    return f"{tipo} {numero} canal {canal}" if numero is not None else f"{tipo} canal {canal}"


POR_DIRECCION = {direccion(control): control for control in CONTROLES}


# --- 1. Definición de VirtualDJ --------------------------------------------------------------------------------

def leer_device():
    entradas, salidas = {}, {}
    for elemento in ET.parse(DEVICE).getroot():
        nombre = elemento.get("name")
        if elemento.tag in ("button", "slider", "encoder"):
            canal = int(elemento.get("channel")) + 1
            if elemento.get("pitch") == "true":
                clave = ("pitch", None, canal)
            elif elemento.get("cc") is not None:
                clave = ("cc", int(elemento.get("cc"), 0), canal)
            else:
                clave = ("nota", int(elemento.get("note"), 0), canal)
            entradas[nombre] = clave
        elif elemento.tag == "sysex":
            salidas[nombre] = _direccion_de_mensaje(bytes.fromhex(elemento.get("value")))
        elif elemento.tag == "text":
            salidas[nombre] = "pantalla"
    return entradas, salidas


def _direccion_de_mensaje(mensaje):
    estado, canal = mensaje[0] & 0xF0, (mensaje[0] & 0x0F) + 1
    if estado in (0x80, 0x90, 0xA0):
        return ("nota", mensaje[1], canal)
    if estado == 0xB0:
        return ("cc", mensaje[1], canal)
    if estado == 0xE0:
        return ("pitch", None, canal)
    return None


def revisar_device(informe, entradas):
    for nombre, clave in entradas.items():
        control = POR_DIRECCION.get(clave)
        if control is None:
            informe.error(f"VirtualDJ define {nombre} ({nombre_direccion(clave)}) y el contrato no tiene ese control")
        elif control.vdj != nombre:
            informe.error(f"VirtualDJ llama {nombre} a {nombre_direccion(clave)}; el contrato dice {control.vdj}")
    for control in CONTROLES:
        if control.vdj and control.vdj not in entradas:
            informe.error(f"{control.nombre}: el contrato dice que VirtualDJ lo llama {control.vdj}, y no está")
        elif control.vdj and entradas[control.vdj] != direccion(control):
            informe.error(f"{control.nombre}: VirtualDJ lo tiene en {nombre_direccion(entradas[control.vdj])}, "
                          f"el contrato en {nombre_direccion(direccion(control))}")


# --- 2. Elementos del script de Ableton ------------------------------------------------------------------------

def _config_lcd():
    arbol = ast.parse((SCRIPT / "Config.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == "LCD_ENABLED" for t in nodo.targets):
            return bool(ast.literal_eval(nodo.value))
    return True


def _numeros(nodo):
    # create_matrix_identifiers(a, b, ...) o [list(range(a, b))]
    if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", None) == "create_matrix_identifiers":
        return list(range(ast.literal_eval(nodo.args[0]), ast.literal_eval(nodo.args[1])))
    if isinstance(nodo, ast.List) and len(nodo.elts) == 1 and isinstance(nodo.elts[0], ast.Call):
        rango = nodo.elts[0].args[0]
        return list(range(*(ast.literal_eval(arg) for arg in rango.args)))
    return [ast.literal_eval(nodo)]


def leer_elementos():
    """{nombre del elemento: [(tipo, número, canal), ...]} como los arma ControlElements.__init__."""
    lcd = _config_lcd()
    canal_por_defecto = 1 if lcd else 0
    parciales = {"add_button", "add_encoder", "add_button_matrix", "add_modifier_button"}
    arbol = ast.parse((SCRIPT / "ControlElements.py").read_text(encoding="utf-8"))
    clase = next(nodo for nodo in arbol.body if isinstance(nodo, ast.ClassDef) and nodo.name == "ControlElements")
    init = next(nodo for nodo in clase.body if isinstance(nodo, ast.FunctionDef) and nodo.name == "__init__")
    elementos = {}

    def recorrer(sentencias):
        for sentencia in sentencias:
            if isinstance(sentencia, ast.If) and "LCD_ENABLED" in ast.unparse(sentencia.test):
                recorrer(sentencia.body if lcd else sentencia.orelse)
            elif isinstance(sentencia, ast.Expr) and isinstance(sentencia.value, ast.Call):
                llamada(sentencia.value)

    def llamada(nodo):
        funcion = nodo.func
        nombre_funcion = funcion.id if isinstance(funcion, ast.Name) else getattr(funcion, "attr", "")
        if not nombre_funcion.startswith("add_") or nombre_funcion.startswith(("add_sub", "add_modified")):
            return
        claves = {kw.arg: kw.value for kw in nodo.keywords}
        if nombre_funcion == "add_element":
            if "identifier" not in claves:
                return
            nombre, numeros = ast.literal_eval(nodo.args[0]), [ast.literal_eval(claves["identifier"])]
        elif nombre_funcion == "add_sysex_display_line" or len(nodo.args) < 2:
            return
        else:
            numeros, nombre = _numeros(nodo.args[0]), ast.literal_eval(nodo.args[1])
        canal_nodo = claves.get("channel") or claves.get("channels")
        if canal_nodo is not None:
            canal = canal_por_defecto if getattr(canal_nodo, "id", None) == "default_channel" else ast.literal_eval(canal_nodo)
        else:
            canal = canal_por_defecto if isinstance(funcion, ast.Name) and nombre_funcion in parciales else 0
        tipo_mensaje = ast.unparse(claves["msg_type"]) if "msg_type" in claves else ""
        tipo = "pitch" if "PB" in tipo_mensaje else "nota" if "NOTE" in tipo_mensaje else "cc"
        elementos[nombre.lower()] = [(tipo, None if tipo == "pitch" else numero, canal + 1) for numero in numeros]

    recorrer(init.body)
    return elementos


def revisar_elementos(informe, elementos):
    esperados = {}
    for control in CONTROLES:
        if control.ableton:
            base = control.ableton.split("[")[0]
            esperados.setdefault(base, []).append(control)
    for nombre, controles in esperados.items():
        if nombre not in elementos:
            informe.error(f"El contrato usa el elemento '{nombre}' de Ableton y ControlElements.py no lo define")
            continue
        tiene = set(elementos[nombre])
        quiere = {direccion(control) for control in controles}
        for clave in sorted(quiere - tiene, key=str):
            informe.error(f"Ableton '{nombre}' no incluye {nombre_direccion(clave)} ({POR_DIRECCION[clave].nombre})")
        for clave in sorted(tiene - quiere, key=str):
            control = POR_DIRECCION.get(clave)
            otro = f"; en el contrato es {control.nombre} (ableton = {control.ableton})" if control else ""
            informe.error(f"Ableton '{nombre}' incluye {nombre_direccion(clave)}, que el contrato no le da{otro}")
    for nombre in sorted(set(elementos) - set(esperados)):
        informe.error(f"ControlElements.py define '{nombre}' ({nombre_direccion(elementos[nombre][0])}) "
                      f"y el contrato no lo nombra")


# --- 3. Constantes y ruteo del script de Ableton ---------------------------------------------------------------

def cargar_router():
    """MidiRouter.py (el ruteo de verdad del script): no importa nada de Live, así que se carga suelto."""
    spec = importlib.util.spec_from_file_location("MidiRouter", SCRIPT / "MidiRouter.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def leer_constantes(router):
    """Las constantes de MidiRouter.py y las del resto del script (estas sin Live: se leen del texto)."""
    constantes = {nombre: valor for nombre, valor in vars(router).items() if nombre.isupper()}
    nodos = [nodo for archivo in MODULOS_SCRIPT
             for nodo in ast.parse((SCRIPT / archivo).read_text(encoding="utf-8")).body]
    for nodo in nodos:
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name):
            nombre = nodo.targets[0].id
            if not nombre.isupper():
                continue
            try:
                constantes[nombre] = eval(compile(ast.Expression(nodo.value), "<constante>", "eval"),
                                          {"__builtins__": {}, "range": range, "tuple": tuple, **constantes})
            except Exception:
                pass  # Config.X, cadenas armadas en tiempo de ejecución...
    return constantes


def _cc2(numero):
    return ("cc", numero, 2)


def _claves(valor):
    """(0xB1, n), tuplas de esos o un rango de CC -> direcciones."""
    if isinstance(valor, tuple) and len(valor) == 2 and all(isinstance(v, int) for v in valor):
        return [_cc2(valor[1])] if valor[0] == 0xB1 else []
    if isinstance(valor, (tuple, list, dict)):
        return [clave for item in valor for clave in _claves(item)]
    return []


class EntornoPrueba:
    """Lo que el router le pregunta a Live: nada apretado, vista mixer, salvo lo que se pida."""

    def __init__(self, shift=False, tempo=False, **otros):
        self.shift_pressed = shift
        self.solo_pressed = self.erase_pressed = self.mute_pressed = False
        self.macro_pressed = self.plugin_pressed = False
        self.encoder_tempo_mode = tempo
        self.display_mode = "default"
        self.encoder_mode = "tempo" if tempo else "default"
        for nombre, valor in otros.items():
            setattr(self, nombre, valor)


ESTADO_DEL_MODO = {"ableton": {}, "lock": {"pad_lock": True}, "dj": {"vdj_mode": True}, "reposo": {"standby": True}}
# Modificadores del router y en qué modos los usa: apretar uno ahí cuenta como que Ableton reacciona, aunque solo no
# haga nada (cambia lo que hacen los demás botones). SCENE se sigue en todos los modos pero solo sirve en Ableton
MODIFICADORES = {"shift_down": MODOS, "follow_held": MODOS, "restart_held": MODOS, "scene_down": ("ableton", "lock")}


def router_en(router_mod, modo):
    router = router_mod.MidiRouter(standby=False)
    for atributo, valor in ESTADO_DEL_MODO[modo].items():
        setattr(router, atributo, valor)
    return router


def mensaje(control, valor=127):
    """El mensaje MIDI de apretar (o girar, en las perillas) un control del contrato."""
    canal = control.canal - 1
    if control.tipo == "pitch":
        return (0xE0 | canal, 0x00, 0x40)
    if control.tipo == "nota":
        return (0x90 | canal, control.numero, valor)
    return (0xB0 | canal, control.numero, 1 if control.nombre.startswith("KNOB") and canal == 0 else valor)


def ableton_reacciona(router_mod, control, modo):
    """"efecto" si el script hace algo con el control en ese modo (lo deja pasar a Live, cambia de modo o hace algo
    que se ve o se oye), "estado" si solo lo sigue para no perder el hilo, None si lo ignora. Se prueba sin nada
    apretado, con SHIFT y con el encoder en TEMPO."""
    resultado = None
    for shift, tempo in ((False, False), (True, False), (False, True)):
        router = router_en(router_mod, modo)
        router.shift_down = shift
        antes = (router.standby, router.vdj_mode, router.pad_lock)
        modificadores = {nombre: getattr(router, nombre) for nombre, modos in MODIFICADORES.items() if modo in modos}
        efectos = []
        pasa = router.accept(mensaje(control), EntornoPrueba(shift, tempo), lambda nombre, *a: efectos.append(nombre))
        if pasa or antes != (router.standby, router.vdj_mode, router.pad_lock):
            return "efecto"
        if any(getattr(router, nombre) != valor for nombre, valor in modificadores.items()):
            return "efecto"
        if any(nombre not in router_mod.STATE_ONLY_EFFECTS for nombre in efectos):
            return "efecto"
        if any(nombre != "_log" for nombre in efectos):
            resultado = "estado"
    return resultado


def luces_de_ableton(router_mod):
    """Qué direcciones (y la pantalla) deja salir el router en cada modo."""
    pantalla = (0xF0, 0x00, 0x00, 0x66, 0x17, 0x12, 0x00, 0x20, 0xF7)
    luces = {}
    for modo in MODOS:
        router = router_en(router_mod, modo)
        luces[modo] = {direccion(control) for control in CONTROLES if router.lets_out(mensaje(control))}
        if router.lets_out(pantalla):
            luces[modo].add("pantalla")
    return luces


def revisar_constantes(informe, c):
    for nombre, valor in c.items():
        for clave in _claves(valor):
            if clave not in POR_DIRECCION:
                informe.error(f"Script de Ableton: {nombre} usa {nombre_direccion(clave)}, que no está en el contrato")
    for numero, nombre in c.get("BUTTON_NAMES", {}).items():
        control = POR_DIRECCION.get(_cc2(numero))
        if control is None:
            informe.error(f"BUTTON_NAMES: CC {numero} ({nombre}) no está en el contrato")
        elif nombre.upper() != control.nombre.replace("_", "") and nombre.upper() != (control.vdj or "").replace("_", ""):
            informe.aviso(f"BUTTON_NAMES: CC {numero} se llama '{nombre}' en el script y {control.nombre} en el contrato")


def revisar_efectos(informe):
    """Cada efecto que pide el router (run("nombre", ...)) tiene que ser un método del script: si no, falla recién en
    Live, al apretar ese botón."""
    router = (SCRIPT / "MidiRouter.py").read_text(encoding="utf-8")
    metodos = {metodo for archivo in MODULOS_SCRIPT
               for metodo in re.findall(r"^    def (\w+)\(", (SCRIPT / archivo).read_text(encoding="utf-8"), re.M)}
    for nombre in sorted(set(re.findall(r'run\("(\w+)"', router)) - metodos):
        informe.error(f"MidiRouter.py pide el efecto '{nombre}' y el script (ni sus mixins) no tiene ese método")


def revisar_duenos_ableton(informe, router_mod):
    de_oido = []
    for control in CONTROLES:
        modos_de_oido = []
        for modo in MODOS:
            dueno = control.dueno(modo)
            if dueno not in DUENOS:
                informe.error(f"{control.nombre}: dueño '{dueno}' en modo {modo} no existe")
                continue
            if dueno == "ambos" and not control.por_que:
                informe.error(f"{control.nombre}: es de los dos en modo {modo} y no dice por qué")
            ableton_dice = dueno in ("ableton", "ambos")
            hace = ableton_reacciona(router_mod, control, modo)
            if ableton_dice and hace != "efecto":
                informe.error(f"{control.nombre}: el contrato dice que Ableton reacciona en modo {modo} "
                              f"({dueno}), y MidiRouter lo descarta")
            elif hace == "efecto" and not ableton_dice:
                informe.error(f"{control.nombre}: MidiRouter reacciona en modo {modo}, y el contrato dice '{dueno}'")
            elif hace == "estado" and not ableton_dice:
                modos_de_oido.append(modo)
        if modos_de_oido:
            de_oido.append(f"{control.nombre} ({', '.join(modos_de_oido)})")
    if de_oido:
        informe.nota(f"El script de Ableton sigue {len(de_oido)} controles sin hacer nada que se vea (seguimiento de "
                     f"oído): " + ", ".join(de_oido))


# --- 4. mode.py de las pantallas -------------------------------------------------------------------------------

MODE_ESPERADO = {"SAMPLING_CC": "SAMPLING", "MIXER_CC": "MIXER", "PLUGIN_CC": "PLUGIN", "ARRANGER_CC": "ARRANGER",
                 "BROWSER_CC": "BROWSER", "KNOB_TOUCH_CCS": [f"KNOB{n}_TOUCH" for n in range(1, 9)],
                 "PAD_PAGE_CCS": ["PADMODE", "KEYBOARD", "CHORDS", "STEP"],
                 "GROUP_CCS": [f"GROUP_{letra}" for letra in "ABCDEFGH"]}


def revisar_mode_py(informe):
    for ruta in MODE_PY:
        if not ruta.exists():
            continue
        valores = {}
        for nodo in ast.parse(ruta.read_text(encoding="utf-8")).body:
            if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name):
                try:
                    valores[nodo.targets[0].id] = eval(ast.unparse(nodo.value), {"__builtins__": {}, "range": range})
                except Exception:
                    pass
        canal = valores.get("MODE_CHANNEL", 1) + 1
        nombre_ruta = ruta.relative_to(RAIZ.parent)
        for constante, esperado in MODE_ESPERADO.items():
            if constante not in valores:
                informe.aviso(f"{nombre_ruta}: no define {constante}")
                continue
            numeros = list(valores[constante]) if isinstance(esperado, list) else [valores[constante]]
            nombres = [getattr(POR_DIRECCION.get(("cc", numero, canal)), "nombre", f"CC {numero}?") for numero in numeros]
            if nombres != (esperado if isinstance(esperado, list) else [esperado]):
                informe.error(f"{nombre_ruta}: {constante} apunta a {nombres}, el contrato dice {esperado}")


# --- 5. Mapeo de VirtualDJ -------------------------------------------------------------------------------------

def leer_mapper():
    return [(mapa.get("value"), mapa.get("action")) for mapa in ET.parse(MAPPER).getroot() if mapa.tag == "map"]


def revisar_mapper(informe, entradas, salidas, luces_ableton):
    vdj_hace = {modo: {} for modo in MODOS}  # modo -> control -> "efecto" / "estado"
    por_vdj = {control.vdj: control for control in CONTROLES if control.vdj}
    for nombre, accion in leer_mapper():
        if nombre == "ONINIT" or nombre in salidas:
            continue
        control = por_vdj.get(ALIAS_VDJ.get(nombre, nombre)) or POR_NOMBRE.get(ALIAS_VDJ.get(nombre, ""))
        if control is None:
            informe.error(f"El mapeo usa '{nombre}', que no es un control del contrato ni una salida")
            continue
        arbol = Analizador(accion).secuencia()
        for modo in MODOS:
            hechas = acciones(arbol, ENTORNO_VDJ[modo])
            efectos = [" ".join(a) for a in hechas if a[0] not in SOLO_ESTADO]
            if efectos:
                vdj_hace[modo][control.nombre] = ("efecto", efectos)
            elif any(a[0] in ("set", "toggle") for a in hechas):
                vdj_hace[modo].setdefault(control.nombre, ("estado", []))

    de_oido, libres = [], []
    for control in CONTROLES:
        modos_de_oido = []
        for modo in MODOS:
            dueno = control.dueno(modo)
            clase, efectos = vdj_hace[modo].get(control.nombre, (None, []))
            if clase == "efecto" and dueno not in ("vdj", "ambos"):
                muestra = "; ".join(dict.fromkeys(efectos))[:140]
                informe.error(f"{control.nombre}: VirtualDJ reacciona en modo {modo} ({muestra}), "
                              f"y el contrato dice '{dueno}'")
            elif clase == "estado" and dueno in ("ableton", "nadie"):
                modos_de_oido.append(modo)
            elif clase is None and dueno == "ambos":
                informe.aviso(f"{control.nombre}: el contrato dice que es de los dos en modo {modo} y VirtualDJ no lo usa")
            elif clase is None and dueno == "vdj" and modo == "dj":
                libres.append(control.nombre)
        if modos_de_oido:
            de_oido.append(f"{control.nombre} ({', '.join(modos_de_oido)})")
    if de_oido:
        informe.nota(f"VirtualDJ anota una variable sin hacer nada audible, para no perder el hilo (seguimiento de "
                     f"oído), en {len(de_oido)} controles: " + ", ".join(de_oido))
    if libres:
        informe.nota(f"Libres en modo DJ (VirtualDJ no los usa): {', '.join(libres)}")

    acciones_salida = dict(leer_mapper())
    en_reposo = []
    for nombre, destino in salidas.items():
        if destino is None or nombre not in acciones_salida:
            continue
        arbol = Analizador(acciones_salida[nombre]).secuencia()
        for modo in MODOS:
            entorno = ENTORNO_VDJ[modo]
            escribe = bool(acciones(arbol, entorno)) if destino == "pantalla" else condicion(arbol, entorno) is not False
            if not escribe:
                continue
            if modo == "reposo":
                en_reposo.append(_destino(destino))
            if destino in luces_ableton[modo]:
                control = POR_DIRECCION.get(destino)
                explicado = PANTALLA_COMPARTIDA if destino == "pantalla" else getattr(control, "luz_compartida", "")
                if not explicado:
                    informe.error(f"{nombre}: VirtualDJ escribe {_destino(destino)} en modo {modo}, "
                                  f"y Ableton también la maneja ahí")
    if en_reposo:
        informe.nota(f"En reposo (todo apagado) VirtualDJ todavía puede escribir: {', '.join(dict.fromkeys(en_reposo))}")


def _destino(destino):
    if destino == "pantalla":
        return "la pantalla"
    control = POR_DIRECCION.get(destino)
    return f"la luz de {control.nombre}" if control else nombre_direccion(destino)


# --- 6. Protocolo entre programas ------------------------------------------------------------------------------

PROTOCOLO = RAIZ / "contrato" / "protocolo.py"
COPIAS_PROTOCOLO = (SCRIPT / "Protocolo.py", RAIZ / "Pantallas" / "prototipo" / "protocolo.py")


def revisar_protocolo(informe, arreglar):
    fuente = PROTOCOLO.read_bytes()
    for copia in COPIAS_PROTOCOLO:
        if copia.exists() and copia.read_bytes().replace(b"\r\n", b"\n") == fuente.replace(b"\r\n", b"\n"):
            continue
        if arreglar:
            copia.write_bytes(fuente)
            informe.nota(f"{copia.relative_to(RAIZ)}: copiado de nuevo desde contrato/protocolo.py")
        else:
            informe.error(f"{copia.relative_to(RAIZ)} no es igual a contrato/protocolo.py (--arreglar lo copia)")
    # Ningún archivo tiene que tener un puerto escrito a mano: todos salen de protocolo.py
    valores = {}
    exec(compile(fuente, str(PROTOCOLO), "exec"), valores)
    puertos = {valor: nombre for nombre, valor in valores.items() if nombre.endswith("_PORT")}
    patron = re.compile(r"\b(" + "|".join(str(p) for p in puertos) + r")\b")
    archivos = [*SCRIPT.glob("*.py"), *(RAIZ / "Pantallas").rglob("*.py"), *(RAIZ / "Pantallas").glob("*.bat"),
                *(RAIZ / "tools").glob("*.py")]
    for archivo in archivos:
        if archivo in COPIAS_PROTOCOLO or ".venv" in archivo.parts:
            continue
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for encontrado in patron.findall(linea):
                informe.error(f"{archivo.relative_to(RAIZ)}:{numero}: el puerto {encontrado} está escrito a mano "
                              f"(usar protocolo.{puertos[int(encontrado)]})")


# --- Tabla y salida --------------------------------------------------------------------------------------------

def tabla():
    corto = {"ableton": "Ableton", "vdj": "VDJ", "ambos": "AMBOS", "nadie": "-"}
    filas = [("Control", "MIDI") + tuple(m.capitalize() for m in MODOS)]
    for control in CONTROLES:
        filas.append((control.nombre, nombre_direccion(direccion(control)))
                     + tuple(corto[control.dueno(m)] for m in MODOS))
    anchos = [max(len(fila[i]) for fila in filas) for i in range(len(filas[0]))]
    return "\n".join("  ".join(celda.ljust(ancho) for celda, ancho in zip(fila, anchos)) for fila in filas)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tabla", action="store_true", help="mostrar la tabla de dueños por modo")
    parser.add_argument("--todo", action="store_true", help="mostrar también lo informativo")
    parser.add_argument("--arreglar", action="store_true", help="volver a copiar contrato/protocolo.py a sus copias")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    informe = Informe()
    entradas, salidas = leer_device()
    revisar_device(informe, entradas)
    revisar_elementos(informe, leer_elementos())
    router = cargar_router()
    revisar_constantes(informe, leer_constantes(router))
    revisar_duenos_ableton(informe, router)
    revisar_efectos(informe)
    revisar_mode_py(informe)
    revisar_mapper(informe, entradas, salidas, luces_de_ableton(router))
    revisar_protocolo(informe, args.arreglar)

    if args.tabla:
        print(tabla(), end="\n\n")
    secciones = [("ERRORES", informe.errores), ("AVISOS", informe.avisos)]
    if args.todo:
        secciones.append(("INFO", informe.info))
    for titulo, lineas in secciones:
        print(f"{titulo} ({len(lineas)})")
        for linea in dict.fromkeys(lineas):
            print(f"  - {linea}")
        print()
    print(f"{len(CONTROLES)} controles en el contrato. "
          f"{len(informe.errores)} errores, {len(informe.avisos)} avisos, {len(informe.info)} notas"
          + ("" if args.todo else " (--todo para verlas)"))
    return 1 if informe.errores else 0


if __name__ == "__main__":
    sys.exit(main())
