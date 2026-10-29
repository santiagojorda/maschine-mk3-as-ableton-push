# Propuesta Técnica y Arquitectura: Sincronización de Tempo VDJ ↔ Ableton (Sin Ableton Link)

## 1. Visión General y Objetivos

### El Problema
Al tocar en vivo con **VirtualDJ** como reproductor principal y **Ableton Live 12** como motor de efectos, clips o sintetizadores, sincronizarlos mediante **Ableton Link** tradicional suele presentar inconvenientes críticos:
1. **Pérdida de independencia:** Ableton Link intenta forzar sincronización de fase/grid continua por red. Si en VirtualDJ se realiza un pitch bend manual con la rueda de control (jogwheel), scratch o un ajuste dinámico, Link puede arrastrar bruscamente a Live generando artefactos de audio o saltos en pistas de warping.
2. **Falta de visibilidad:** Al ajustar el tempo en la Maschine MK3 (botón `TEMPO`), la pantalla solo muestra el BPM interno de Ableton, obligando al usuario a mirar la pantalla de la computadora para saber a qué BPM corre el tema en VirtualDJ.

### La Solución Propuesta
Un sistema de **sincronización de tempo a demanda (One-Shot Snap Sync) sin Ableton Link**, que ofrece:
- **Lectura en vivo en pantalla:** Al pulsar o tocar `TEMPO` en Maschine MK3, la pantalla derecha muestra simultáneamente el tempo de Ableton y el BPM en tiempo real del deck activo de VirtualDJ.
- **Botón físico de igualación instantánea:** Al presionar hacia abajo el **Encoder 4D (`EncoderPush`)** mientras se está en modo TEMPO (o mediante el atajo `SHIFT + TAP`), Ableton iguala su BPM de inmediato al de VirtualDJ (`song.tempo = vdj_bpm`).
- **Independencia total:** Sin sincronización de fase invasiva. Ableton adopta el BPM exacto de la pista que suena en VDJ sin que Live quede atado a la red ni sufra micro-cortes si se manipulan los platos en VirtualDJ.

---

## 2. Flujo de Datos y Arquitectura de Comunicación

VirtualDJ y el ecosistema de pantallas de la Maschine ya cuentan con canales de telemetría establecidos. La arquitectura aprovecha estos conductos sin necesidad de instalar cables virtuales adicionales ni consumir CPU apreciable.

```
┌────────────────────────────────────────────────────────┐
│                      VirtualDJ                         │
│  - Exporta deck {n} get_bpm (BPM * 1000) por SysEx     │
│  - Exporta playing, sync (M=Master), volumen           │
└──────────────────────────┬─────────────────────────────┘
                           │ SysEx MIDI (Puerto "MK3 Screens")
                           ▼
┌────────────────────────────────────────────────────────┐
│                     vdj_puerto.py                      │
│  - Mantiene el puerto virtual abierto                  │
│  - Reenvía campos decodificados por UDP local          │
└──────────────────────────┬─────────────────────────────┘
                           │ UDP 127.0.0.1:9019
                           ▼
┌────────────────────────────────────────────────────────┐
│             Driver Pantallas (dj_screens.py)           │
│  - Contiene instancia VdjData() con decks[0], decks[1] │
│  - Identifica el Deck Maestro / Deck en reproducción    │
│  - Renderiza gráficos LCD (480x272 c/u)                │
└──────────────┬───────────────────────────▲─────────────┘
               │                           │
               │ UDP Telemetría (9017)     │ Retorno UDP / Inbound (9021)
               │ (Ableton -> Screens)      │ (VDJ BPM -> Ableton)
               ▼                           │
┌────────────────────────────────────────────────────────┐
│         Ableton Live 12 (CustomMaschineMK3)            │
│  - Modo encoder: "tempo"                               │
│  - Botón: EncoderPush (botón 8)                        │
│  - Acción: self.song.tempo = vdj_bpm                   │
└────────────────────────────────────────────────────────┘
```

### 2.1. Extracción de Datos desde VirtualDJ
VirtualDJ ya tiene mapeado en `vdj/generar.py` el campo de BPM:
- **Código de campo 3 (BPM):** `deck {n} get_bpm & param_multiply 1000 & param_cast 'integer'`
- **Código de campo 5 (PLAY):** `deck {n} play ? get_text '1' : get_text '0'`
- **Código de campo 8 (SYNC/MASTER):** `deck {n} masterdeck ? get_text 'M' : ...`

El módulo `vdj_data.py` decodifica esto en tiempo real:
```python
vdj_bpm = vdj_data.decks[deck_idx].get("bpm")  # Ejemplo: 126.50
is_playing = vdj_data.decks[deck_idx].get("playing")
is_master = vdj_data.decks[deck_idx].get("sync") == "M"
```

### 2.2. Algoritmo de Selección del "Deck de Referencia"
Para determinar cuál es el tempo de VirtualDJ a mostrar y sincronizar:
1. **Prioridad 1 (Master Deck):** Si algún deck tiene la bandera `masterdeck` (`sync == 'M'`), se toma ese deck.
2. **Prioridad 2 (Deck en Play):** Si ningún deck es master explícito, se toma el deck que tenga `playing == True`. Si ambos suenan, se toma el que tenga mayor volumen audible.
3. **Prioridad 3 (Último cargado/activo):** Si ambos están detenidos, se toma el último deck reproducido o cargado.
4. **Fallback:** Si VirtualDJ no está corriendo o no hay temas cargados, el sistema marca `VDJ: Inactivo`.

### 2.3. Envío del BPM de VDJ hacia Ableton Live
Existen dos alternativas sencillas y de muy baja latencia:
- **Alternativa A (Socket UDP de Retorno - Recomendada):**
  `dj_screens.py` envía un paquete UDP ligero a `127.0.0.1:9021` cada vez que el BPM del deck activo cambia o cuando Ableton reporta estar en modo `tempo`.
  En `CustomMaschineMK3`, un socket no bloqueante (`socket.SOCK_DGRAM`, `setblocking(False)`) lee el paquete dentro del ciclo `_screen_bridge_tick` (~33 ms).
- **Alternativa B (Archivo de Estado / Shared Memory):**
  `dj_screens.py` escribe `vdj_tempo.json` en `DATA_DIR` con el BPM activo. `CustomMaschineMK3` lo lee cuando se presiona el botón de sincronización. (Ventaja: cero sockets nuevos; Desventaja: I/O de disco si no se usa RAM/mmap).

---

## 3. Diseño de la Interfaz en Pantalla (UI / UX)

### Ubicación: Pantalla Derecha (Display 1 - Encoder View)
Cuando el usuario pulsa el botón **TEMPO** en la Maschine MK3, la pantalla derecha pasa a dibujar el modo encoder de tempo ([`encoder_view.py`](file:///c:/Users/jorda/Documentos/PROYECTOS/ABLETON/maschine-mk3-driver/prototipo/encoder_view.py)).

Actualmente esa pantalla solo muestra:
- Barra superior morada: `TEMPO` | `ABLETON`
- Número grande: `124.00 BPM`
- Fader horizontal de 60 a 200 BPM

### Nueva Disposición Propuesta (Dual-Readout & Sync Indicator)

```
┌────────────────────────────────────────────────────────┐
│  TEMPO (ABLETON)                  VDJ DECK 1: 126.50   │  <-- Encabezado con estado
├────────────────────────────────────────────────────────┤
│                                                        │
│   LIVE: 124.00 BPM        VDJ: 126.50 BPM              │  <-- Lectura comparativa
│   [ Gira: Ajuste fino ]   [ Δ +2.50 BPM ]              │  <-- Diferencia de tempo
│                                                        │
│   ══════════════════════════════════════════════════   │  <-- Fader con doble marca
│                                                        │
│         🔘 APRETÁ ENCODER PARA SINCRONIZAR             │  <-- Call To Action activo
└────────────────────────────────────────────────────────┘
```

#### Estados Visuales:
1. **Desfasados (`|Ableton - VDJ| > 0.05 BPM`):**
   - El badge de VDJ resalta en cian/naranja.
   - Se muestra la diferencia: por ejemplo, `Δ +2.50 BPM` o `Δ -1.20 BPM`.
   - El botón de acción dice: `🔘 APRETÁ ENCODER PARA IGUALAR`.
2. **Sincronizados (`|Ableton - VDJ| <= 0.05 BPM`):**
   - El indicador central cambia a **verde esmeralda**.
   - Texto: `✓ TEMPOS IGUALADOS (126.50 BPM)`.
   - Se muestra un icono de candado o check.
3. **VirtualDJ Cerrado o Sin Audio:**
   - La sección de VDJ muestra: `VDJ: -- (Sin pista)`.
   - El encoder funciona en su modo tradicional de Ableton sin dar errores.

---

## 4. Asignación de Hardware (Botones Físicos)

### 4.1. Botón Principal: `EncoderPush` (Presionar el Encoder 4D)
- **Por qué:** En la configuración actual de [`Mappings.py:123-126`](file:///c:/Users/jorda/Documentos/PROYECTOS/ABLETON/maschine-mk3-as-ableton-push/Ableton/CustomMaschineMK3/Mappings.py#L123-L126), en modo `tempo`:
  ```python
  tempo = dict(
      component = "Transport",
      tempo_coarse_encoder = "encoder",
      tempo_fine_encoder = "encoder_with_shift"
  )
  ```
  **¡El botón `encoderpush` (presionar el encoder hacia abajo) está completamente libre y sin mapear!**
- **Ergonomía:** Es el gesto más natural para un DJ o productor:
  - Girar la perilla = modificar el tempo manualmente.
  - Presionar la perilla = **"Snap/Igualar al tempo de VirtualDJ"**.

### 4.2. Botón Secundario (Atajo Global): `SHIFT + TAP`
- Si el usuario no quiere entrar al modo TEMPO en pantallas, pulsar `SHIFT + TAP` (o mantener `TAP` mientras se presiona `TEMPO`) dispara de inmediato la misma igualación, mostrando en la barra de mensajes de Ableton:
  `"Tempo sincronizado con VirtualDJ: 126.50 BPM"`.

### 4.3. Botón de Pantalla: Botón 8 sobre la Pantalla Derecha
- En los 8 botones sobre las pantallas, el botón 8 puede iluminarse con la leyenda `SYNC VDJ` sobre la pantalla LCD. Al pulsarlo, ejecuta la misma sincronización.

---

## 5. Lógica de Ejecución en Código (Especificación)

### En `CustomMaschineMK3.py`:
```python
def _sync_tempo_with_virtualdj(self):
    """Iguala el tempo de Ableton al BPM activo de VirtualDJ sin Ableton Link."""
    vdj_bpm = self._latest_vdj_bpm
    if vdj_bpm and 40.0 <= vdj_bpm <= 250.0:
        self.song.tempo = round(vdj_bpm, 2)
        self._c_instance.show_message(f"Tempo sincronizado a VirtualDJ: {self.song.tempo:.2f} BPM")
        self._send_screen_bridge_state()  # Refresca pantallas de inmediato
```

### En el manejador del EncoderPush:
```python
if self.component_map["Encoder_Modes"].selected_mode == "tempo":
    self._sync_tempo_with_virtualdj()
```

---

## 6. Ventajas Clave de este Enfoque

| Característica | Ableton Link Tradicional | Sincronización Manual One-Shot (Propuesta) |
| :--- | :--- | :--- |
| **Micro-cortes / Freezes** | Riesgo de tirones si la red o el buffer oscilan. | **Cero riesgo:** Es solo una asignación de variable en memoria local. |
| **Control en Jogs/Platos** | Mover el plato en VDJ puede forzar warping no deseado en Live. | **Totalmente independiente:** Live mantiene su BPM fijo hasta que decidas volver a pulsar. |
| **Visibilidad en Maschine** | No dice qué deck manda ni qué tema suena. | **Muestra el BPM exacto de VDJ, el deck y el delta en la pantalla LCD.** |
| **Ergonomía** | Requiere activar Link en ambos softwares. | **1 botón físico directo en la Maschine MK3 (`EncoderPush`).** |

---

## 7. Próximos Pasos para la Implementación

1. **Paso 1:** Agregar en `encoder_view.py` la recepción de `vdj_data` para renderizar el BPM de VDJ junto al de Ableton cuando el modo sea `TEMPO`.
2. **Paso 2:** Habilitar un canal UDP no bloqueante en `CustomMaschineMK3` para recibir `vdj_bpm` desde el driver de pantallas.
3. **Paso 3:** Mapear `encoderpush` en el modo `tempo` de `Mappings.py` para invocar `_sync_tempo_with_virtualdj()`.
4. **Paso 4:** Probar la respuesta en vivo con temas a distintos BPM en VirtualDJ.
