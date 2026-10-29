"""Lee las acciones del mapeo de VirtualDJ (VDJScript) para revisarlas y simularlas fuera de VirtualDJ.

  analizar(texto)                      -> árbol de la acción
  acciones(arbol, entorno)             -> todas las acciones que PUEDEN correr, con las variables que se conocen
  condicion(arbol, entorno)            -> True / False / None (no se sabe sin VirtualDJ corriendo)
  ejecutar(arbol, variables, valor)    -> corre la acción de verdad: cambia las variables ($...) y devuelve lo
                                          que VirtualDJ haría (deck, crossfader...); lo que pregunta por un deck o
                                          por el browser se toma como falso

Lo usan tools/validar_contrato.py y los tests (tests/test_escenarios.py).
"""


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


def analizar(texto):
    return Analizador(texto).secuencia()


def _variable(palabra):
    return palabra.strip("'")


def condicion(nodo, entorno):
    """True / False / None (no se sabe sin VirtualDJ corriendo)."""
    if nodo[0] == "atomo":
        palabras = nodo[1]
        if palabras == ["true"]:
            return True
        if palabras == ["false"]:
            return False
        if len(palabras) in (2, 3) and palabras[0] == "var":
            variable = _variable(palabras[1])
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


# --- Escribir legible y compactar ------------------------------------------------------------------------------

ANCHO = 100


def compactar(texto):
    """El texto de una acción en una sola línea, con un espacio entre tokens (VirtualDJ ignora los espacios)."""
    salida = ""
    for token in tokenizar(texto):
        if salida and not salida.endswith("(") and token != ")":
            salida += " "
        salida += token
    return salida


def _grupos(tokens):
    """Los tokens de un nivel, con cada (...) como una lista adentro."""
    pila = [[]]
    for token in tokens:
        if token == "(":
            pila.append([])
        elif token == ")" and len(pila) > 1:
            grupo = pila.pop()
            pila[-1].append(grupo)
        else:
            pila[-1].append(token)
    while len(pila) > 1:  # paréntesis sin cerrar: se dejan como estaban
        grupo = pila.pop()
        pila[-1].extend(["("] + grupo)
    return pila[0]


def _plano(nivel):
    partes = []
    for item in nivel:
        partes += ["(", *_plano(item), ")"] if isinstance(item, list) else [item]
    return partes


def _formatear(nivel, sangria):
    plano = compactar(" ".join(_plano(nivel)))
    if len(plano) + len(sangria) <= ANCHO or not any(t in ("?", ":", "&") for t in nivel):
        return [sangria + _en_linea(nivel, sangria)]
    # Corta en los ? / : / & de este nivel; los (...) largos van en líneas propias, más adentro
    lineas, actual = [], []
    for item in nivel:
        if item in ("?", ":", "&") and actual:
            lineas.append(actual)
            actual = []
        actual.append(item)
    lineas.append(actual)
    salida = []
    for numero, linea in enumerate(lineas):
        prefijo = sangria if numero == 0 else sangria + "    "
        salida += _linea_con_grupos(linea, prefijo)
    return salida


def _en_linea(nivel, sangria):
    return compactar(" ".join(_plano(nivel)))


def _linea_con_grupos(linea, prefijo):
    texto = compactar(" ".join(_plano(linea)))
    if len(prefijo) + len(texto) <= ANCHO:
        return [prefijo + texto]
    # El último (...) de la línea, si es largo, se abre en un bloque
    cabeza = linea[:-1] if isinstance(linea[-1], list) else linea
    cola = linea[-1] if isinstance(linea[-1], list) else None
    if cola is None:
        return [prefijo + texto]
    inicio = compactar(" ".join(_plano(cabeza)))
    return ([prefijo + (inicio + " (" if inicio else "(")] + _formatear(cola, prefijo + "    ")
            + [prefijo + ")"])


def formatear(texto):
    """Una acción de una línea, en varias líneas sangradas por anidamiento (compactar() la vuelve a una)."""
    return "\n".join(_formatear(_grupos(tokenizar(texto)), ""))


# --- Ejecutar con valores concretos ----------------------------------------------------------------------------

def _pregunta(palabras, variables, valor):
    """Valor de verdad de un átomo usado como condición."""
    if palabras == ["true"]:
        return True
    if palabras == ["false"] or not palabras:
        return False
    verbo = palabras[0]
    if verbo == "var" and len(palabras) >= 2:
        actual = variables.get(_variable(palabras[1]), 0)
        return actual != 0 if len(palabras) == 2 else actual == float(palabras[2])
    if verbo in ("param_bigger", "param_greater", "param_smaller") and len(palabras) == 2:
        limite = float(palabras[1].rstrip("%")) / (100.0 if palabras[1].endswith("%") else 1.0)
        return valor > limite if verbo != "param_smaller" else valor < limite
    if verbo in ("var_smaller", "var_greater") and len(palabras) == 3:
        actual = variables.get(_variable(palabras[1]), 0)
        return actual < float(palabras[2]) if verbo == "var_smaller" else actual > float(palabras[2])
    return False  # preguntas a un deck, al browser...: sin VirtualDJ, falso


def _verdad(nodo, variables, valor):
    if nodo[0] == "atomo":
        return _pregunta(nodo[1], variables, valor)
    if nodo[0] == "si":
        rama = nodo[2] if _verdad(nodo[1], variables, valor) else nodo[3]
        return _verdad(rama, variables, valor)
    return False


def ejecutar(nodo, variables, valor=1.0):
    """Corre la acción: cambia `variables` y devuelve la lista de lo que VirtualDJ haría (textos)."""
    hechas = []

    def correr(nodo):
        if nodo[0] == "sec":
            for item in nodo[1]:
                correr(item)
        elif nodo[0] == "si":
            correr(nodo[2] if _verdad(nodo[1], variables, valor) else nodo[3])
        else:
            palabras = nodo[1]
            if not palabras or palabras[0] in ("nothing", "true", "false", "repeat_start", "repeat_stop"):
                return
            if palabras[0] == "set" and len(palabras) >= 3:
                variables[_variable(palabras[1])] = float(palabras[2])
            elif palabras[0] == "toggle" and len(palabras) >= 2:
                nombre = _variable(palabras[1])
                variables[nombre] = 0.0 if variables.get(nombre, 0) else 1.0
            elif palabras[0] not in ("var", "get_text", "param_cast"):
                hechas.append(" ".join(palabras))

    correr(nodo)
    return hechas
