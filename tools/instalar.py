"""Instala el script de Ableton y el mapeo de VirtualDJ desde el repo (o desde cualquier rama) en un solo paso.

Antes de copiar:
  - corre tools/validar_contrato.py y los tests (tests/) y no instala si algo falla (--sin-validar lo saltea; con
    --ref no se valida, porque los dos miran la carpeta del repo y no esa rama);
  - guarda lo que está instalado en %LOCALAPPDATA%\\MaschineMK3AsPush\\respaldos\\<fecha>, para volver con --restaurar.

Destinos:
  - Ableton: cada C:\\ProgramData\\Ableton\\*\\Resources\\MIDI Remote Scripts\\Maschine_as_Push que exista (los .py;
    settings.json y el .log de esa carpeta no se tocan)
  - VirtualDJ: %LOCALAPPDATA%\\VirtualDJ\\Devices y \\Mappers
Las pantallas no: corren desde Pantallas\\dist (Pantallas\\construir_exe.bat).

Uso:  python tools/instalar.py --simular          muestra qué haría, sin copiar nada
      python tools/instalar.py                    instala lo que está en la carpeta del repo (la rama actual)
      python tools/instalar.py --ref main         instala la rama main, sin cambiar de rama (para volver a lo estable)
      python tools/instalar.py --restaurar        vuelve a poner el último respaldo
Después: reiniciar Live (o elegir otra superficie de control y volver) y reiniciar VirtualDJ.
"""

import argparse
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
NOMBRE_INSTALADO = "Maschine_as_Push"
ORIGEN_SCRIPT = "Ableton/CustomMaschineMK3"
ORIGEN_VDJ = {"VirtualDJ/Devices/MaschineMK3-VDJ.xml": "Devices",
              "VirtualDJ/Mappers/MASCHINEMK3VDJ - Mapeo Personalizado.xml": "Mappers"}
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", ""))
RESPALDOS = LOCALAPPDATA / "MaschineMK3AsPush" / "respaldos"
VIRTUALDJ = LOCALAPPDATA / "VirtualDJ"


def destinos_ableton():
    patron = os.path.join(r"C:\ProgramData\Ableton", "*", "Resources", "MIDI Remote Scripts", NOMBRE_INSTALADO)
    # glob no ve las carpetas que empiezan con punto (".Live 12 Suite_updated") con "*": se buscan aparte
    rutas = set(glob.glob(patron)) | set(glob.glob(patron.replace("*", ".*")))
    return sorted(Path(ruta) for ruta in rutas)


def _git(*args):
    return subprocess.run(["git", "-C", str(RAIZ), *args], check=True, capture_output=True).stdout


def archivos(ref):
    """[(ruta en el repo, contenido)] de lo que se instala, desde la carpeta del repo o desde una rama de git."""
    if ref is None:
        rutas = [p.relative_to(RAIZ).as_posix() for p in sorted((RAIZ / ORIGEN_SCRIPT).glob("*.py"))]
        return [(ruta, (RAIZ / ruta).read_bytes()) for ruta in rutas + list(ORIGEN_VDJ)]
    nombres = _git("ls-tree", "--name-only", f"{ref}:{ORIGEN_SCRIPT}").decode("utf-8").split()
    rutas = [f"{ORIGEN_SCRIPT}/{nombre}" for nombre in nombres if nombre.endswith(".py")]
    return [(ruta, _git("show", f"{ref}:{ruta}")) for ruta in rutas + list(ORIGEN_VDJ)]


def plan(contenidos):
    """[(origen en el repo, destino, contenido)]"""
    pasos = []
    for destino in destinos_ableton():
        pasos += [(ruta, destino / Path(ruta).name, datos) for ruta, datos in contenidos if ruta.startswith(ORIGEN_SCRIPT)]
    for ruta, carpeta in ORIGEN_VDJ.items():
        datos = dict(contenidos)[ruta]
        pasos.append((ruta, VIRTUALDJ / carpeta / Path(ruta).name, datos))
    return pasos


def respaldar(pasos):
    # Archivos numerados y un indice.json con el destino de cada uno: copiar la ruta completa adentro del
    # respaldo pasaría el límite de 260 caracteres de Windows
    carpeta = RESPALDOS / datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    carpeta.mkdir(parents=True, exist_ok=True)
    indice = {}
    for numero, (_, destino, _) in enumerate(pasos):
        if destino.exists():
            copia = f"{numero:03d}_{destino.name}"
            shutil.copy2(destino, carpeta / copia)
            indice[copia] = str(destino)
    (carpeta / "indice.json").write_text(json.dumps(indice, indent=1, ensure_ascii=False), encoding="utf-8")
    return carpeta


def validar():
    contrato = subprocess.run([sys.executable, str(RAIZ / "tools" / "validar_contrato.py")])
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(RAIZ / "tests")])
    return contrato.returncode == 0 and tests.returncode == 0


def restaurar(simular):
    respaldos = sorted(p.parent for p in RESPALDOS.glob("*/indice.json")) if RESPALDOS.exists() else []
    if not respaldos:
        print(f"No hay respaldos en {RESPALDOS}")
        return 1
    ultimo = respaldos[-1]
    print(f"Restauro {ultimo}")
    for copia, destino in json.loads((ultimo / "indice.json").read_text(encoding="utf-8")).items():
        print(f"  {destino}")
        if not simular:
            shutil.copy2(ultimo / copia, destino)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", help="rama o commit de git a instalar (por defecto, la carpeta del repo)")
    parser.add_argument("--simular", action="store_true", help="mostrar qué haría, sin copiar")
    parser.add_argument("--restaurar", action="store_true", help="volver a poner el último respaldo")
    parser.add_argument("--sin-validar", action="store_true", help="no correr validar_contrato.py antes")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.restaurar:
        return restaurar(args.simular)
    if not destinos_ableton():
        print(f"No encontré ninguna carpeta {NOMBRE_INSTALADO} en C:\\ProgramData\\Ableton")
        return 1
    if args.ref is None and not args.sin_validar and not validar():
        print("El contrato o los tests fallan: no instalo (--sin-validar para instalar igual)")
        return 1

    origen = f"la rama {args.ref}" if args.ref else f"la carpeta del repo ({_git('branch', '--show-current').decode().strip()})"
    pasos = plan(archivos(args.ref))
    cambian = [(ruta, destino, datos) for ruta, destino, datos in pasos
               if not destino.exists() or destino.read_bytes() != datos]
    print(f"Instalo desde {origen}: {len(cambian)} de {len(pasos)} archivos cambian")
    for ruta, destino, _ in cambian:
        print(f"  {ruta}  ->  {destino}")
    sobrantes = [archivo for destino in destinos_ableton() for archivo in destino.glob("*.py")
                 if archivo.name not in {Path(ruta).name for ruta, _ in archivos(args.ref) if ruta.endswith(".py")}]
    for archivo in sobrantes:
        print(f"  (queda instalado y no está en el origen: {archivo})")
    if args.simular or not cambian:
        print("Nada copiado." if args.simular else "Ya estaba instalado.")
        return 0

    print(f"Respaldo: {respaldar(cambian)}")
    for _, destino, datos in cambian:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
        cache = destino.parent / "__pycache__"
        if destino.suffix == ".py" and cache.exists():
            for compilado in cache.glob(destino.stem + ".*.pyc"):
                compilado.unlink()
    print("Listo. Reiniciá Live (o cambiá de superficie de control y volvé) y reiniciá VirtualDJ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
