# 📋 Plan de Arquitectura: Driver Nativo para Maschine MK3

**Fecha:** 2026-10-07 / Actualizado: 2026-10-08  
**Objetivo:** Reemplazar el software de fondo de Native Instruments por un driver liviano y de código abierto diseñado para **Ableton Live 12** y el flujo tipo **Ableton Push**.

---

## 🎯 Objetivo General

Reemplazar los servicios residentes de Native Instruments en segundo plano por un driver propio de alto rendimiento, optimizado para la integración con **[maschine-mk3-as-ableton-push](https://github.com/santiagojorda/maschine-mk3-as-ableton-push)**:

- **Modo Ableton Live 12:** Todo funciona de forma nativa e interactiva con el Remote Script `CustomMaschineMK3`.
- **Renderizado de pantallas:** Telemetría en tiempo real recibida vía socket UDP local (puerto 9017) y dibujada a 20+ FPS en las dos pantallas LCD a color (480×272 c/u).
- **Control de hardware:** Lectura HID directa para pads, perillas, botones y encoders; actualización de LEDs por reportes HID.
- **Portabilidad futura:** Preparado para correr en Windows 11 (Windows MIDI Services) y compilar para Linux (Push 3 standalone / Raspberry Pi).

---

## 📐 Decisiones de Diseño

| Tema | Decisión | Fundamento |
|---|---|---|
| **Lenguaje del Driver Definitivo** | Go | Binario único y autocontenido sin dependencias externas, bajo consumo de CPU/RAM, fácil compilación cruzada para Windows y Linux. |
| **Prototipo Rápido Inicial** | Python 3.12 | Permite iteración inmediata de layouts gráficos (Pillow, NumPy) y validación del protocolo USB bulk antes de pasar a binario estático. |
| **Protocolo de Pantallas** | USB Bulk (Interface 5) | Endpoint bulk `0x04`, 2 × 480×272 píxeles en RGB565. Acceso mediante WinUSB (asignado con Zadig). |
| **Protocolo de Controles** | USB HID (Interface 4) | Reportes de entrada `0x01` (botones/perillas) y `0x02` (pads con presión). No requiere modificar drivers de NI para la entrada. |
| **Puertos MIDI Virtuales** | loopMIDI / Windows MIDI Services | Comunicación bidireccional de baja latencia hacia la DAW. |

---

## 🔌 Especificaciones del Hardware (Maschine MK3)

- **Identificadores USB:** Vendor ID `0x17CC`, Product ID `0x1600`.
- **Entradas HID:** Interfaz 4, endpoint `0x83`.
  - Reporte `0x01`: Estado de botones y perillas en mapa de bits.
  - Reporte `0x02`: Presión y velocidad de los 16 pads (hasta 21 bloques de 3 bytes).
- **LEDs:**
  - Reporte `0x80`: 63 bytes para LEDs monocromáticos de botones.
  - Reporte `0x81`: 42 bytes para LEDs RGB indexados (pads, grupos, encoder).
- **Pantallas LCD:** Interfaz 5, endpoint bulk `0x04`.
  - Dos displays de 480 × 272 píxeles, formato de color RGB565 (16 bits por píxel en big-endian).
  - Cabecera de 16 bytes: `0x84`, ID de pantalla (`0` o `1`), `0x60`, seguidos de coordenadas rectangulares $(X, Y, W, H)$.
  - Comando de longitud de datos, bloque de píxeles, delimitador de dibujo `0x03` y cierre de paquete `0x40`.
  - Permite refresco parcial de rectángulos sucios (*dirty rects*) para máxima eficiencia.

---

## 🗺️ Fases del Proyecto

### Fase 1: Driver de Pantallas (Completada en Prototipo)
- Configuración de WinUSB en interfaz 5 mediante Zadig.
- Recepción de telemetría UDP desde Ableton Live en formato estructurado.
- Renderizado de vistas gráficas:
  - **Session View:** Matriz de clips y escenas con marcos dinámicos.
  - **Mixer View:** Faders de canal, potenciómetros, medidores VU y mute/solo.
  - **Device View:** Parámetros de instrumentos y efectos con perillas gráficas.
  - **Browser View:** Árbol de navegación y preescucha de muestras.
  - **Encoder Overlay:** Indicadores de volumen Master, Cue y tempo.
- Empaquetado en ejecutable autocontenido `MaschineMK3AsPush.exe` con supervisor de reconexión automática.

### Fase 2: Entrada HID y Puertos MIDI en Go
- Implementación de lector HID en hilo dedicado con prioridad en tiempo real (MMCSS Pro Audio).
- Decodificación de eventos de botones, encoders táctiles y touch strip.
- Curvas de sensibilidad y fixed velocity para pads.
- Creación de interfaz virtual MIDI sin necesidad de utilitarios externos.

### Fase 3: Gestión Completa de LEDs
- Driver para reportes `0x80` y `0x81`.
- Retroalimentación visual bidireccional desde Ableton Live (colores de pista, estado de clips, metrónomo y transporte).

### Fase 4: Optimización y Standby
- Modo reposo inteligente (<kbd>SHIFT</kbd> + <kbd>CHANNEL</kbd>): apagado de iluminación y salvapantallas de bajo consumo para proteger las pantallas LCD.
- Consumo objetivo: < 1% de CPU en reposo y respuesta inmediata ante cualquier pulsación.

---

## ⚡ Estimación de Latencia

| Tramo | Estimación | Nota |
|---|---|---|
| Maschine → PC (Reporte HID) | ~1.0 ms | Intervalo estándar de sondeo USB |
| Decodificación del Driver | < 0.1 ms | Procesamiento en memoria sin asignaciones dinámicas |
| Driver → Ableton Live (MIDI) | < 0.5 ms | Comunicación por pipe o puerto virtual de baja latencia |
| Buffer de Audio de Live | 3–8 ms | Configurado por el usuario en su interfaz de audio |
| **Total Pad a Audio** | **4.5–9.5 ms** | Latencia idéntica a hardware dedicado |
