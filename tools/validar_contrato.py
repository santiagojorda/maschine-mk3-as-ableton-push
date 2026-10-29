"""Compara contrato/controles.py con lo que está escrito a mano en cada programa y busca controles con dos dueños.

Qué revisa:
  1. VirtualDJ/Devices/MaschineMK3-VDJ.xml: cada control con el mismo número, canal y nombre que el contrato.
  2. Ableton/CustomMaschineMK3/ControlElements.py: lo mismo con los elementos del script.
  3. Las constantes de CustomMaschineMK3.py: que cada (0xB1, n) sea un control del contrato, y que los dueños del
     contrato coincidan con lo que hace _accept_midi en cada modo (ver _ableton_reacciona).
  4. mode.py de las pantallas (las dos copias, si están): los botones que cambian el modo.
  5. El mapeo de VirtualDJ: evalúa cada acción en cada modo ($vdj, $pads, $padlock) y avisa si VirtualDJ hace algo
     con un control que el contrato le da solo a Ableton, o si prende una luz que Ableton también maneja.

Uso:  python tools/validar_contrato.py            errores y avisos
      python tools/validar_contrato.py --tabla    además, la tabla de dueños por modo
      python tools/validar_contrato.py --todo     además, lo informativo (seguimiento "de oído", controles libres)
Sale con código 1 si hay errores.
"""

import argparse
import ast
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from contrato.controles import CONTROLES, DUENOS, MODOS, PANTALLA_COMPARTIDA, POR_NOMBRE  # noqa: E402

DEVICE = RAIZ / "VirtualDJ" / "Devices" / "MaschineMK3-VDJ.xml"
MAPPER = RAIZ / "VirtualDJ" / "Mappers" / "MASCHINEMK3VDJ - Mapeo Personalizado.xml"
SCRIPT = RAIZ / "Ableton" / "CustomMaschineMK3"
MODE_PY = (RAIZ / "Pantallas" / "prototipo" / "mode.py", RAIZ.parent / "maschine-mk3-driver" / "prototipo" / "mode.py")

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


# --- 3. Constantes del script y lo que hace _accept_midi -------------------------------------------------------

def leer_constantes():
    arbol = ast.parse((SCRIPT / "CustomMaschineMK3.py").read_text(encoding="utf-8"))
    constantes = {}
    for nodo in arbol.body:
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


def _ableton_reacciona(c):
    """Lo que hace _accept_midi (CustomMaschineMK3.py) en cada modo, armado con sus constantes.
    Si cambia _accept_midi, esto se tiene que actualizar a mano: la fase 3 lo reemplaza por el ruteo de verdad."""
    solo_vdj = {("nota", nota, c["VDJ_ONLY_CHANNEL"] + 1) for nota in c["VDJ_ONLY_NOTES"]}
    zona_pads = ({("nota", nota, 1) for nota in c["PAD_NOTES"]} | {("pitch", None, 1), ("pitch", None, 2)}
                 | {_cc2(cc) for cc in c["GROUP_BUTTON_CCS"]} | set(_claves(c["PAD_PAGE_BUTTONS"])))
    lock = _cc2(c["PAD_LOCK_BUTTON"][1])
    # En modo DJ: los de Ableton siempre, el modo del encoder, los que salen, y los casos con condición de _accept_midi:
    # SHIFT (se sigue arriba de todo), SHIFT + CHANNEL (reposo), SHIFT + MACRO, TEMPO (y el encoder en modo TEMPO), LOCK
    en_dj = (set(_claves(c["ABLETON_ALWAYS_BUTTONS"])) | set(_claves(c["SHARED_ENCODER_MODE_BUTTONS"]))
             | set(_claves(c["VDJ_EXIT_BUTTONS"])) | set(_claves([c["SESSION_VIEW_BUTTON"], c["VDJ_ENTER_BUTTON"],
                                                                   c["SHIFT_BUTTON"], c["STANDBY_BUTTON"],
                                                                   c["MACRO_BUTTON"], c["TEMPO_BUTTON"],
                                                                   c["ENCODER_TURN_BUTTON"]])) | {lock})
    en_reposo = set(_claves(c["STANDBY_WAKE_BUTTONS"])) | set(_claves([c["VDJ_ENTER_BUTTON"]]))
    todos = {direccion(control) for control in CONTROLES}
    return {
        "ableton": todos - solo_vdj,
        "lock": (todos - solo_vdj - zona_pads) | {lock},
        "dj": en_dj,
        "reposo": en_reposo,
    }, zona_pads | {lock}


def _luces_de_ableton(c, zona_pads_y_lock):
    """Qué luces manda el script en cada modo (_do_send_midi)."""
    solo_vdj = {("nota", nota, c["VDJ_ONLY_CHANNEL"] + 1) for nota in c["VDJ_ONLY_NOTES"]}
    todas = {direccion(control) for control in CONTROLES} | {"pantalla"}
    return {
        "ableton": todas - solo_vdj,
        "lock": todas - solo_vdj - zona_pads_y_lock,
        "dj": set(_claves(c["ABLETON_ALWAYS_BUTTONS"])),
        "reposo": set(),
    }


def revisar_constantes(informe, c):
    for nombre, valor in c.items():
        for clave in _claves(valor):
            if clave not in POR_DIRECCION:
                informe.error(f"CustomMaschineMK3.py: {nombre} usa {nombre_direccion(clave)}, que no está en el contrato")
    for numero, nombre in c.get("BUTTON_NAMES", {}).items():
        control = POR_DIRECCION.get(_cc2(numero))
        if control is None:
            informe.error(f"BUTTON_NAMES: CC {numero} ({nombre}) no está en el contrato")
        elif nombre.upper() != control.nombre.replace("_", "") and nombre.upper() != (control.vdj or "").replace("_", ""):
            informe.aviso(f"BUTTON_NAMES: CC {numero} se llama '{nombre}' en el script y {control.nombre} en el contrato")


def revisar_duenos_ableton(informe, reacciona):
    for control in CONTROLES:
        for modo in MODOS:
            dueno = control.dueno(modo)
            if dueno not in DUENOS:
                informe.error(f"{control.nombre}: dueño '{dueno}' en modo {modo} no existe")
                continue
            if dueno == "ambos" and not control.por_que:
                informe.error(f"{control.nombre}: es de los dos en modo {modo} y no dice por qué")
            ableton_dice = dueno in ("ableton", "ambos")
            ableton_hace = direccion(control) in reacciona[modo]
            if ableton_dice and not ableton_hace:
                informe.error(f"{control.nombre}: el contrato dice que Ableton reacciona en modo {modo} "
                              f"({dueno}), y _accept_midi lo descarta")
            elif ableton_hace and not ableton_dice:
                informe.error(f"{control.nombre}: _accept_midi lo deja pasar en modo {modo}, "
                              f"y el contrato dice '{dueno}'")


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

def tokenizar(texto):
    tokens, i = [], 0
    while i < len(texto):
        caracter = texto[i]
        if caracter.isspace():
            i += 1
        elif caracter in "()&?:":
            tokens.append(caracter)
            i += 1
        elif caracter in "'\"`":
            fin = texto.find(caracter, i + 1)
            fin = len(texto) - 1 if fin < 0 else fin
            tokens.append(texto[i:fin + 1])
            i = fin + 1
        else:
            fin = i
            while fin < len(texto) and not texto[fin].isspace() and texto[fin] not in "()&?:'\"`":
                fin += 1
            tokens.append(texto[i:fin])
            i = fin
    return tokens


class Analizador:
    """VDJScript: a & b encadena; c ? x : y elige. El ? toma la acción de su izquierda (x & c ? y : z = x & (c ? y : z))
    y la rama del : es un solo término. Si VirtualDJ agrupara distinto, se verían de más acciones, no de menos."""

    def __init__(self, texto):
        self.tokens, self.i = tokenizar(texto), 0

    def ver(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def tomar(self):
        token = self.ver()
        self.i += 1
        return token

    def secuencia(self):
        items = [self.termino()]
        while self.ver() == "&":
            self.tomar()
            items.append(self.termino())
        return items[0] if len(items) == 1 else ("sec", items)

    def termino(self):
        primario = self.primario()
        if self.ver() != "?":
            return primario
        self.tomar()
        entonces = self.secuencia()
        sino = ("atomo", ["nothing"])
        if self.ver() == ":":
            self.tomar()
            sino = self.termino()
        return ("si", primario, entonces, sino)

    def primario(self):
        if self.ver() == "(":
            self.tomar()
            interno = self.secuencia()
            if self.ver() == ")":
                self.tomar()
            return interno
        palabras = []
        while self.ver() not in (None, "&", "?", ":", "(", ")"):
            palabras.append(self.tomar())
        return ("atomo", palabras)


def condicion(nodo, entorno):
    """True / False / None (no se sabe sin VirtualDJ corriendo)."""
    if nodo[0] == "atomo":
        palabras = nodo[1]
        if palabras == ["true"]:
            return True
        if palabras == ["false"]:
            return False
        if len(palabras) in (2, 3) and palabras[0] == "var":
            variable = palabras[1].strip("'")
            if variable not in entorno:
                return None
            if len(palabras) == 2:
                return entorno[variable] != 0
            try:
                return entorno[variable] == float(palabras[2])
            except ValueError:
                return None
        return None
    if nodo[0] == "si":
        cumple = condicion(nodo[1], entorno)
        if cumple is True:
            return condicion(nodo[2], entorno)
        if cumple is False:
            return condicion(nodo[3], entorno)
        a, b = condicion(nodo[2], entorno), condicion(nodo[3], entorno)
        return a if a == b else None
    return None


def acciones(nodo, entorno):
    if nodo[0] == "atomo":
        return [nodo[1]] if nodo[1] else []
    if nodo[0] == "sec":
        return [accion for item in nodo[1] for accion in acciones(item, entorno)]
    cumple = condicion(nodo[1], entorno)
    if cumple is True:
        return acciones(nodo[2], entorno)
    if cumple is False:
        return acciones(nodo[3], entorno)
    return acciones(nodo[2], entorno) + acciones(nodo[3], entorno)


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
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    informe = Informe()
    entradas, salidas = leer_device()
    revisar_device(informe, entradas)
    revisar_elementos(informe, leer_elementos())
    constantes = leer_constantes()
    revisar_constantes(informe, constantes)
    reacciona, zona_pads_y_lock = _ableton_reacciona(constantes)
    revisar_duenos_ableton(informe, reacciona)
    revisar_mode_py(informe)
    revisar_mapper(informe, entradas, salidas, _luces_de_ableton(constantes, zona_pads_y_lock))

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
