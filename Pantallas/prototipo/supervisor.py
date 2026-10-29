"""Supervisor de las pantallas: mantiene vivos vdj_puerto.py y dj_screens.py.

- vdj_puerto.py (puerto de datos de VirtualDJ): lo lanza primero, para que exista antes
  de que se abra VirtualDJ, y lo vuelve a lanzar si muere.
- dj_screens.py: lo lanza y lo reinicia si se cierra o si se cuelga (deja de escribir su
  pulso, .venv/dj_screens.heartbeat). Si se cae seguido, espera cada vez más entre intentos.
- Todo lo que imprime dj_screens.py va a .venv/pantallas.log con la hora; el registro se
  rota al pasar de 5 MB (queda el anterior como pantallas.log.1).

Una sola instancia: si ya hay uno corriendo (por ejemplo, el del inicio de Windows), sale.

Uso: python supervisor.py      (en una consola: además muestra el registro)
     pythonw supervisor.py     (sin ventana: así lo arranca Windows al iniciar sesión)
"""

import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from paths import DATA_DIR, child_command

HERE = Path(__file__).resolve().parent
LOG_PATH = DATA_DIR / "pantallas.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
HEARTBEAT_FILE = DATA_DIR / "dj_screens.heartbeat"
STOP_FILE = DATA_DIR / "detener"  # dj_screens.py lo mira y se cierra solo, terminando el cuadro que manda
ALREADY_RUNNING = 2
DATED_LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")
SINGLE_INSTANCE_ADDRESS = ("127.0.0.1", 9020)
HEARTBEAT_TIMEOUT = 15.0  # sin pulso por más que esto = colgado
STARTUP_GRACE = 30.0  # al arrancar puede tardar (Windows recién iniciado, la Maschine apagada...)
CHECK_EVERY = 1.0
RESTART_MIN_SECONDS = 5.0  # entre dos reinicios pedidos desde la Maschine


class Log:
    def __init__(self, path):
        self._path = path
        self._lock = threading.Lock()
        self._console = sys.stdout if sys.stdout is not None and sys.stdout.isatty() else None

    def write(self, text, stamp=True):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text.rstrip()}\n" if stamp else f"{text.rstrip()}\n"
        with self._lock:
            try:
                if self._path.exists() and self._path.stat().st_size > LOG_MAX_BYTES:
                    backup = self._path.with_suffix(".log.1")
                    if backup.exists():
                        backup.unlink()
                    self._path.rename(backup)
                with open(self._path, "a", encoding="utf-8") as file:
                    file.write(line)
            except OSError:
                pass
            if self._console is not None:
                try:
                    self._console.write(line)
                    self._console.flush()
                except (OSError, UnicodeError):
                    pass


def kill_tree(pid):
    # El python del venv es un lanzador que abre el python real: hay que matar el árbol entero
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def heartbeat_age():
    try:
        return time.time() - HEARTBEAT_FILE.stat().st_mtime
    except OSError:
        return None


class Screens:
    """dj_screens.py como proceso hijo, con su salida al registro."""

    def __init__(self, log):
        self._log = log
        self.process = None
        self.started = 0.0
        self.failures = []  # horas de las últimas caídas, para esperar más si se cae seguido
        self.last_requested = 0.0

    def start(self):
        environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self.process = subprocess.Popen(
            child_command("screens"), cwd=str(DATA_DIR),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
        self.started = time.time()
        threading.Thread(target=self._copy_output, args=(self.process,), daemon=True).start()
        self._log.write(f"[supervisor] dj_screens.py arrancó (pid {self.process.pid})")

    def _copy_output(self, process):
        for raw in process.stdout:
            line = raw.decode("utf-8", "replace")
            # Las líneas del registro de las pantallas ya traen fecha; las demás (un error de Python, por ejemplo) no
            self._log.write(line, stamp=not DATED_LINE.match(line))

    def stop_gracefully(self, timeout=8.0):
        """Pide el cierre ordenado y espera; matarlo a la fuerza en medio de una transferencia USB puede dejar
        a la Maschine esperando el resto de un cuadro."""
        if self.process is None:
            return
        STOP_FILE.write_text("1", encoding="ascii")
        try:
            self.process.wait(timeout=timeout)
            self._log.write("[supervisor] dj_screens.py se cerró en orden")
        except subprocess.TimeoutExpired:
            self._log.write("[supervisor] dj_screens.py no cerró a tiempo: lo fuerzo")
            kill_tree(self.process.pid)
        STOP_FILE.unlink(missing_ok=True)
        self.process = None

    def stop(self, reason):
        if self.process is None:
            return
        self._log.write(f"[supervisor] reinicio dj_screens.py: {reason}")
        kill_tree(self.process.pid)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        self.process = None
        now = time.time()
        self.failures = [moment for moment in self.failures if now - moment < 300] + [now]

    def restart_requested(self):
        """Pedido desde la Maschine (SHIFT + MACRO): cierra las pantallas en orden; check() las vuelve a lanzar.
        Con un mínimo entre pedidos, para que apretarlo varias veces no apile reinicios."""
        if time.time() - self.last_requested < RESTART_MIN_SECONDS:
            self._log.write("[supervisor] pedido de reinicio ignorado: hace muy poco que se reinició")
            return
        self.last_requested = time.time()
        self._log.write("[supervisor] reinicio de las pantallas pedido desde la Maschine (SHIFT + MACRO)")
        self.stop_gracefully(timeout=4.0)

    def backoff(self):
        # 2 s la primera vez, y el doble por cada caída de los últimos 5 minutos, hasta 60 s
        return min(60.0, 2.0 * 2 ** max(0, len(self.failures) - 1))

    def check(self):
        if self.process is None:
            self.start()
            return
        code = self.process.poll()
        if code is not None:
            self.stop(f"se cerró (código {code})")
            time.sleep(self.backoff())
            self.start()
            return
        age = heartbeat_age()
        if time.time() - self.started > STARTUP_GRACE and (age is None or age > HEARTBEAT_TIMEOUT):
            self.stop(f"colgado (sin pulso hace {age:.0f} s)" if age is not None else "sin pulso")
            time.sleep(self.backoff())
            self.start()


def vdj_port_running():
    from vdj_data import BRIDGE_ADDRESS
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(BRIDGE_ADDRESS)
        return False
    except OSError:
        return True
    finally:
        probe.close()


_port_process = None  # el puerto de datos que lanzó este supervisor


def start_vdj_port(log):
    global _port_process
    _port_process = subprocess.Popen(
        child_command("port", windowless=True), cwd=str(DATA_DIR),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    log.write("[supervisor] lancé vdj_puerto.py (VirtualDJ se reconecta solo)")


def main():
    sys.path.insert(0, str(HERE))
    lock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        lock.bind(SINGLE_INSTANCE_ADDRESS)
    except OSError:
        if sys.stdout is not None:
            print(f"Ya hay un supervisor corriendo. El registro está en {LOG_PATH}")
        return ALREADY_RUNNING
    lock.setblocking(False)  # por ahí llega "salir" (maschine_mk3.py --salir)

    log = Log(LOG_PATH)
    log.write("[supervisor] arrancó")
    screens = Screens(log)
    last_port_check = 0.0
    try:
        while True:
            if time.time() - last_port_check > 5.0:
                last_port_check = time.time()
                if not vdj_port_running():
                    start_vdj_port(log)
                    time.sleep(1.0)  # que el puerto exista antes de que dj_screens.py lo busque
            try:
                message = lock.recvfrom(64)[0]
                if message == b"salir":
                    log.write("[supervisor] cerrado con --salir")
                    break
                if message == b"reiniciar":
                    screens.restart_requested()
            except OSError:
                pass  # nada pendiente
            screens.check()
            time.sleep(CHECK_EVERY)
    except KeyboardInterrupt:
        log.write("[supervisor] cerrado con Ctrl+C")
    finally:
        screens.stop_gracefully()
        if _port_process is not None and _port_process.poll() is None:
            kill_tree(_port_process.pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
