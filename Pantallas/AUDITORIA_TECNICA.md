# 🛡️ Auditoría Técnica y Hoja de Ruta: Maschine MK3 as Ableton Push

Documento técnico de diagnóstico, arquitectura, optimización y resiliencia para el ecosistema **Maschine MK3 as Ableton Push** (Remote Script en Ableton Live 12 + Driver de Pantallas USB).

---

## 📌 Tabla de Contenidos
1. [Revisión y Detección de Leaks de Memoria](#1-revisión-y-detección-de-leaks-de-memoria)
2. [Arquitectura y Desacoplamiento](#2-arquitectura-y-desacoplamiento)
3. [Buenas Prácticas de Código y Polimorfismo](#3-buenas-prácticas-de-código-y-polimorfismo)
4. [Eficiencia del Protocolo](#4-eficiencia-del-protocolo)
5. [Reducción de Mensajes y Procesamiento](#5-reducción-de-mensajes-y-procesamiento)
6. [Tolerancia a Fallos y Resiliencia en Vivo](#6-tolerancia-a-fallos-y-resiliencia-en-vivo)
7. [Plan de Acción por Fases](#7-plan-de-acción-por-fases)

---

## 1. Revisión y Detección de Leaks de Memoria

### 1.1. Diagnóstico por Etapas del Flujo VirtualDJ / Captura
* **Etapa GDI / Win32 (`window_capture.py`):**
  * **Estado:** Correctamente blindado con bloques `finally`.
  * **Verificación continua:** Los handles de Windows (`user32.GetWindowDC`, `gdi32.CreateCompatibleDC`, `gdi32.CreateCompatibleBitmap`) deben destruirse estrictamente en cada frame (`DeleteObject`, `DeleteDC`, `ReleaseDC`).
  * **Límite crítico del SO:** 10.000 Objetos GDI por proceso. Superar esta cifra causa fallo gráfico total en Windows.
* **Etapa Hilo de Fondo (`BackgroundWindowCapture`):**
  * **Estado:** Sobrescritura directa de variable única (`self._latest = image`).
  * **Regla:** Mantener puntero simple sin acumular colecciones ni listas históricas de fotogramas.
* **Etapa Pillow / NumPy (`stack_regions`):**
  * Los bitmaps recortados y canvas intermedios residen en ámbito (*scope*) local y son recolectados por el Garbage Collector (GC).
  * **Alerta de Churn:** Cada captura Full HD genera ~8 MB de buffer temporal. Para evitar saturar el GC, se recomienda reutilizar un buffer binario preasignado (`bytearray` fijo) en lugar de instanciar `ctypes.create_string_buffer` 20 veces por segundo.

### 1.2. Protocolo de Monitoreo en Vivo (Prueba de Estrés 2 Horas)
* **Objetos GDI:** Debe permanecer plano entre **20 y 60**. Si supera 200 de forma incremental, hay fuga de handle.
* **RAM Privada (Working Set):** Tras los primeros 3 a 5 minutos, debe estabilizarse en una **meseta plana** (rango nominal: **110 MB – 160 MB**).
* **Handles del Proceso:** Rango nominal estable (**150 – 350**).

---

## 2. Arquitectura y Desacoplamiento

### 2.1. Desarme de la God Class (`CustomMaschineMK3.py` — 1574 líneas)
Actualmente, la clase central concentra más de 80 métodos con múltiples responsabilidades cruzadas:
* Parsing de bytes MIDI en crudo.
* Lógica de transporte y disparo de clips.
* Ruteo hacia VirtualDJ y bloqueo de pads (*pad lock*).
* Servidor y socket UDP de telemetría de pantallas.
* Renderizado lógico de Session Ring, Mixer y Browser.

### 2.2. Nueva Estructura Modular Sugerida
```text
Ableton/CustomMaschineMK3/
├── core/
│   ├── constants.py          # Enums de MIDI, canales, CCs y temporizaciones
│   └── logger.py
├── state/
│   ├── base_state.py         # Interfaz ControllerState
│   ├── ableton_state.py      # Lógica pura de Ableton Push
│   ├── vdj_state.py          # Lógica pasarela VirtualDJ
│   └── standby_state.py      # Lógica de reposo y ahorro de energía
├── components/
│   ├── session_nav.py        # Navegación 4D encoder
│   ├── session_volume.py     # Gestión de perillas y faders de sesión
│   └── screen_bridge.py      # Socket UDP, temporizador y serialización
└── CustomMaschineMK3.py      # Orquestador liviano (< 150 líneas)
```

### 2.3. Eliminación de Flags de Estado Acopladas
Sustituir el conjunto de variables booleanas globales (`_standby`, `_vdj_mode`, `_pad_lock`, `_shift_down`, `_restart_held`, `_follow_held`) por componentes de estado con ciclo de vida definido.

---

## 3. Buenas Prácticas de Código y Polimorfismo

### 3.1. Erradicación de Números Mágicos (Magic Numbers)
Reemplazar los literales distribuidos por enumeraciones de enteros fuertemente tipadas:

```python
from enum import IntEnum

class MidiStatus(IntEnum):
    CC_CH2 = 0xB1
    NOTE_ON_CH2 = 0x91
    NOTE_OFF_CH2 = 0x81

class MaschineCC(IntEnum):
    SAMPLING = 39
    MIXER = 37
    PLUGIN = 35
    CHANNEL = 34
    ARRANGER = 36
    BROWSER = 38
    FOLLOW = 56
    SHIFT = 119
    RESTART = 53
    SOLO = 91
    MUTE = 92
```

### 3.2. Implementación de Patrones de Diseño

#### A. Patrón State (Máquina de Estados de la Controladora)
Elimina las más de 180 líneas de condicionales anidados en `_accept_midi`:
* `StandbyState`: Solo procesa combinaciones de despertar (`SHIFT+CHANNEL`, `MIXER`, `SAMPLING`).
* `VdjState`: Filtra los controles pertenecientes a VirtualDJ y deriva `PLAY`, `STOP`, `TAP` a Live.
* `AbletonState`: Ejecuta el flujo principal de producción e interpretación.

#### B. Patrón Strategy (Renderizado Gráfico en `ableton_ui.py`)
Reemplazar las bifurcaciones basadas en strings (`screen_kind(state)`) por clases de renderizado polimórficas:
* `SessionScreenRenderer`: Matriz 8×4 de clips, estados de reproducción y anillo de pads.
* `MixerScreenRenderer`: Faders verticales, medidores de pico (vúmetros) y paneo.
* `DeviceScreenRenderer`: Arcos de knobs y nombres de parámetros.
* `BrowserScreenRenderer`: Explorador de carpetas y navegación de presets.

#### C. Patrón Command (Modificadores de Perillas)
Estructurar combinaciones (`MUTE + knob`, `SOLO + knob`, `RESTART + knob`, `ERASE + knob`) como comandos aislados, facilitando el agregado de nuevas funciones sin generar regresiones en el código existente.

---

## 4. Eficiencia del Protocolo

### 4.1. Canal USB Bulk de las Pantallas (`maschine_display.py`)
* **Especificaciones:** Endpoint `0x04`, Interfaz `5`, 2 pantallas de 480×272 px, formato **RGB565 Big Endian** (~5 MB/s de rendimiento sostenido).
* **Optimización por Franjas (`changed_rects`):**
  * Mantener el envío diferencial por franjas pares de 120 px.
  * Si ningún elemento gráfico cambia en un intervalo (por ejemplo, sin clips reproduciéndose ni perillas en movimiento), no transmitir datos vacíos al bus USB.

### 4.2. Telemetría UDP (Script de Live ➔ Driver de Pantallas)
* **Estado Actual:** Serialización de un diccionario JSON completo de ~1.5 KB cada 33 ms (~30 veces por segundo).
* **Optimización Propuesta:**
  * **Dirty Check:** Solo emitir el paquete cuando al menos un parámetro numérico varíe por encima de un umbral (`delta > 0.005`).
  * **Evolución a Formato Compacto:** Para valores de alta frecuencia (8 knobs y medidores VU), emplear empaquetado binario (`struct.pack` < 64 bytes) y reservar el JSON únicamente para eventos de baja frecuencia (cambio de nombres de track o cambio de vista).

---

## 5. Reducción de Mensajes y Procesamiento

### 5.1. Eliminación del Bloqueo Síncrono `sleep(0.0005)`
* **Diagnóstico:** En `CustomMaschineMK3._do_send_midi`, cada mensaje enviado aplica `sleep(0.0005)` en el hilo principal de Python de Live.
* **Solución:** Utilizar la infraestructura de cola de mensajes nativa del framework de Ableton v3 (`schedule_message` / buffer de chunks), garantizando cero micro-bloqueos en el procesamiento de eventos de Live.

### 5.2. Memorización de Mediciones de Texto (Caching Pillow)
* En `ableton_ui.py`, la rutina `_fit_text` ejecuta `draw.textlength()` iterativamente para ajustar textos largos a los anchos de columna.
* **Solución:** Implementar `@lru_cache(maxsize=256)` sobre la función de ajuste y truncado de cadenas para evitar recálculos redundantes en cada fotograma.

---

## 6. Tolerancia a Fallos y Resiliencia en Vivo

### 6.1. Garantía del Motor de Audio
* El motor de audio ASIO de Ableton Live corre en C++ en un hilo de tiempo real de máxima prioridad.
* Ningún error, saturación o reinicio del script de Python de las pantallas puede interrumpir ni generar chasquidos en la salida de audio de la sesión.

### 6.2. Auto-Reconexión USB
* En `maschine_display.py`, el bloque `try/except usb.core.USBError` ejecuta `_reopen()` automáticamente ante micro-cortes o fluctuaciones de energía en el puerto USB.

### 6.3. Vigilancia mediante Supervisor (`supervisor.py`)
* Monitoreo activo de pulso (*heartbeat*) cada segundo.
* Si el proceso gráfico `dj_screens.py` no reporta actividad durante más de 15 segundos, el supervisor lo termina y lo relanza de forma automática en menos de 2 segundos.
* Rotación fija de archivos de log a **5 MB** para prevenir agotamiento de espacio en disco o memoria.

### 6.4. Configuración Crítica del Sistema Operativo
* **Plan de Energía:** Modo "Máximo Rendimiento".
* **Suspensión Selectiva de USB:** Deshabilitada en las opciones avanzadas de energía de Windows para evitar que el sistema suspenda la Interfaz 5 de la Maschine.

---

## 7. Plan de Acción por Fases

| Fase | Tarea Principal | Impacto |
|:---:|---|---|
| **Fase 1** | Validación de estabilidad (Prueba de estrés de 2 horas con monitor de RAM y GDI). | Seguridad en vivo inmediata. |
| **Fase 2** | Erradicación de números mágicos creando `constants.py` con `IntEnum`. | Legibilidad y mantenimiento. |
| **Fase 3** | Eliminación de `sleep(0.0005)` en la transmisión MIDI de Live. | Cero latencia en el hilo de UI de Live. |
| **Fase 4** | Refactorización de `_accept_midi` aplicando el patrón **State**. | Código limpio, testeable y sin espagueti. |
| **Fase 5** | Optimización del renderizador de UI (`ableton_ui.py`) con patrón **Strategy** y caché de texto. | Reducción de carga de CPU en un 40%. |
