# 🔬 Prototipo de Pantallas: Maschine MK3 Display Server

Documentación técnica del pipeline de renderizado y comunicación USB para las dos pantallas LCD a color (480×272 c/u) de la Native Instruments Maschine MK3 ejecutando la interfaz de **Ableton Live 12**.

---

## 💡 Concepto y Arquitectura

El servidor de pantallas intercepta el flujo de trabajo sin interferir con las entradas MIDI ni requerir la suite completa de software de Native Instruments activa:

1. **Aislamiento de la Interfaz USB:**
   - La Maschine MK3 expone múltiples interfaces compuestas en Windows.
   - Con **Zadig**, se asigna el controlador **WinUSB** únicamente a la **Interfaz 5** (Bulk Display).
   - Los pads, botones y perillas permanecen en la Interfaz 4 (HID) y son leídos normalmente por el sistema operativo y la DAW.

2. **Recepción de Datos desde Ableton Live:**
   - El script MIDI `CustomMaschineMK3` dentro de Ableton Live transmite el estado de la sesión vía **UDP (puerto 9017)** hacia `127.0.0.1`.
   - Se transmiten eventos estructurados JSON:
     - Nombres y colores de pistas.
     - Vúmetros estéreo en tiempo real.
     - Posición de faders de volumen y envíos auxiliares.
     - Parámetros de efectos y sintetizadores (8 perillas asignadas).
     - Grilla de clips (Session View) y estados de reproducción.
     - Árbol y carpetas del explorador de sonidos (Browser View).

3. **Pipeline Gráfico:**
   - **Lienzo:** Pillow (PIL) genera dos imágenes en memoria de 480×272 píxeles.
   - **Conversión de Color:** NumPy convierte los arreglos RGB a formato **RGB565** (16 bits empaquetados por píxel en formato Big-Endian).
   - **Tasa de refresco:** Entre 20 y 30 FPS con renderizado condicional (solo se reenvían rectángulos modificados para ahorrar ancho de banda USB).

---

## 🛠️ Estructura del Paquete USB

El protocolo de pantallas de Native Instruments (basado en ingeniería inversa de `ni-controllers-lib`) utiliza el endpoint bulk `0x04`:

```
+---------------+----------------+----------------+----------------+
|  Byte 0: 0x84 |  Byte 1: 0x00  | Byte 2: Screen |  Byte 3: 0x60  |
+---------------+----------------+----------------+----------------+
|  Bytes 4 - 7  |   X, Y (16-bit big endian)                       |
+---------------+----------------+----------------+----------------+
|  Bytes 8 - 11 |   Ancho, Alto (16-bit big endian)                |
+---------------+----------------+----------------+----------------+
|  Bytes 12-15  |   Comando 0x00 + (cantidad de píxeles / 2)       |
+---------------+----------------+----------------+----------------+
|  Payload      |   Píxeles en formato RGB565 (2 bytes c/u)        |
+---------------+----------------+----------------+----------------+
|  Tail         |   0x03 0x00 0x00 0x00 (Comando dibujar)          |
|               |   0x40 0x00 0x00 0x00 (Comando finalizar cuadro) |
+---------------+----------------+----------------+----------------+
```

---

## 🛡️ Supervisor y Tolerancia a Fallos

El módulo `supervisor.py` (empaquetado en el ejecutable `MaschineMK3AsPush.exe`) garantiza estabilidad continua en escenarios de producción en vivo:

- **Monitoreo de Heartbeat:** El proceso de renderizado escribe periódicamente una señal de pulso. Si el bus USB se bloquea por un tirón de cable o suspensión de energía, el supervisor detecta la congelación y reinicia el servicio automáticamente.
- **Backoff Exponencial:** En caso de fallas consecutivas, espacia los reintentos para no saturar la CPU ni el bus USB.
- **Cierre Elegante:** Envía una trama de limpieza para dejar las pantallas en negro o en modo standby antes de finalizar.
- **Log Rotativo:** Registra eventos en `%LOCALAPPDATA%\MaschineMK3AsPush\pantallas.log` limitando el tamaño a 5 MB.
