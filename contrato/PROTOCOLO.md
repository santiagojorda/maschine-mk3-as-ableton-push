# Protocolo entre programas

Todo viaja por UDP en `127.0.0.1`. Los números y nombres salen de [`protocolo.py`](protocolo.py) (versión actual: **1**), que tiene dos copias idénticas: `Ableton/CustomMaschineMK3/Protocolo.py` y `Pantallas/prototipo/protocolo.py`. `python tools/validar_contrato.py` avisa si las copias se separan o si algún archivo escribe un puerto a mano.

```
 Script de Ableton ──── 9017 SCREENS_PORT ────►  Pantallas (ableton_text)
        ▲                                          │
        └───────── 9021 VDJ_TEMPO_PORT ────────────┘ (vdj_master)

 VirtualDJ ──MIDI "MK3 Screens"──► vdj_puerto ── 9019 VDJ_DATA_PORT ──► Pantallas (vdj_data)
                                       ▲                                   │
                                       └────── 9018 VDJ_REQUEST_PORT ──────┘

 Script (SHIFT + MACRO), .exe --salir, make stop ── 9020 SUPERVISOR_PORT ──► supervisor
```

Cada JSON lleva `"v"` (la versión). Si al que recibe le llega otra, igual lo usa, pero lo anota una vez en su registro (`pantallas.log` o el `Log.txt` de Live): suele significar que el script y las pantallas se instalaron desde ramas distintas. **Hay que subir `VERSION` cuando un mensaje cambia de forma incompatible**: un campo que se saca, se renombra o cambia de significado. Agregar un campo nuevo no hace falta subirlo.

---

## 9017 · Script de Ableton → Pantallas

Dos clases de paquete por el mismo puerto:

**Líneas MCU** (sysex crudo, no JSON): `F0 00 00 66 17 12 <posición> <caracteres> F7`, con posición = línea × 28. Son las mismas 4 líneas de 28 caracteres que el script le escribe a la Maschine. Se reenvían cada ~1 s, así unas pantallas recién arrancadas tienen texto sin esperar un cambio.

**JSON**, según `"type"`:

| `type` | Cuándo | Campos |
|---|---|---|
| `state` | ~20 veces por segundo en modo Ableton (solo si algo cambió, y al menos cada 0,5 s) | ver abajo |
| `state` con `"standby": true` | en reposo | nada más |
| `mode` | en modo DJ, en cada tick | `"vdj": true`: las pantallas pasan a VirtualDJ aunque hayan arrancado con el modo DJ ya puesto |
| `tempo` | en modo DJ con el encoder en TEMPO | `bpm`: tempo de Live |
| `tempo_flash` | SHIFT + TEMPO igualó el tempo | `bpm`, `seconds`: mostrar la vista de tempo ese tiempo y volver |

Campos de `state`:

| Campo | Qué es |
|---|---|
| `view` | vista del script: `default` (mixer), `device`, `session`, `browser`, `clip`, `settings`... |
| `encoder_mode` | `default`, `volume`, `swing`, `tempo`, `position`, `scale`, `browser`... |
| `encoder` | con VOLUME / SWING / TEMPO: `{mode, value 0-1, text, meter}`; si no, `null` |
| `knobs` | 8 perillas: `{name, value 0-1, text, bipolar, track?, color?, mute?, solo?, meter?}` o `null` |
| `touched`, `touched_all` | perilla tocada (la última) y todas las que se están tocando |
| `no_popup` | MUTE / SOLO / FOLLOW apretado: la perilla actúa sobre su pista, sin pop-up de valor |
| `mixer_parameter` | qué muestran las perillas del mixer (volumen, paneo, envío...) |
| `track`, `track_color`, `locked` | pista que tocan los pads y si está fijada |
| `device`, `device_color` | dispositivo elegido |
| `session_view` | si la vista Session (ARRANGER) está activa |
| `session` | en la vista Session: grilla de 8 pistas × 4 escenas (`tracks`, `scenes`, `track_offset`, `page_offset`, `ring_column`, `ring_tracks`, `scene_offset`, `knob_page`) |
| `grid_frame` | en el mixer: qué columnas están en los pads (`ring_column`, `ring_tracks`) y cuál tiene el cursor (`selected`) |
| `browser`, `browser_grid` | en el browser: carpeta, lista visible alrededor del elemento elegido, carpeta de arriba, preescucha; y la grilla de Session |

Cada columna de `session.tracks`: `{name, color, target, mute, solo, slots}`. Cada slot: `{name, color, playing, triggered, recording, selected?}` si tiene clip, o `{empty, stop, triggered, selected?}`.

## 9021 · Pantallas → Script de Ableton

`vdj_master.py`, cada 0,5 s: `{"v", "t": hora (time.time), "bpm": BPM o null, "deck": 1 / 2 o null}`, con el deck de referencia de VirtualDJ (el master, si no el que más se oye, si no el primero cargado). El script guarda el último y lo usa al apretar SHIFT + TEMPO. Si tiene más de 3 s (`VDJ_TEMPO_MAX_AGE`), avisa que no hay datos.

## 9018 / 9019 · vdj_puerto ↔ Pantallas

`vdj_puerto.py` mantiene abierto el puerto MIDI virtual "MK3 Screens", por donde VirtualDJ manda el estado de los decks (`F0 7D <campo> <texto> F7`, ver `Pantallas/prototipo/vdj/generar.py`). Reenvía cada sysex sin `F0` / `F7` a **9019**. Cuando las pantallas mandan `REQUEST_ALL` (`b"todo"`) a **9018**, vuelve a mandar el último valor de cada campo, marcado con `0x52` ("R") adelante.

### Un solo dueño del modo: el script de Ableton

El script decide el modo (modo DJ y pads fijados con LOCK) y VirtualDJ lo sigue. Así no se desincronizan si uno de los dos se reinicia (`ANALISIS-ACOPLAMIENTO.md`, 3.1 y 3.2):

1. El script lo informa en cada mensaje: `mode` (`"vdj": true`, `"pad_lock"`) y `state` (`"pad_lock"`; en reposo, `"standby": true`, que suelta los dos).
2. `vdj_sync.py` (pantallas) manda `VDJ_SYNC` + 2 bytes (modo DJ 0/1, pads fijados 0/1) a **9018**, apenas cambia y cada segundo. Si el script no avisó en el último segundo (Live cerrado), no manda nada, y VirtualDJ sigue con su propia lógica. Justo después de un botón de modo espera un segundo: los dos programas lo están procesando.
3. `vdj_puerto.py` lo pasa al puerto "MK3 Screens" como dos Control Change en el canal 1: primero `VDJ_SYNC_CC_LOCK` (2) y después `VDJ_SYNC_CC_DJ` (1), con valor 127 (sí) o 0 (no).
4. El mapeo de ese puerto (`ABLETON_LOCK`, `ABLETON_DJ`) corrige `$padlock`, `$vdj` y `$pads` solo si no coinciden. Son variables `$`, globales en VirtualDJ, así que las comparte con el mapeo de la Maschine.

## 9020 · Supervisor de las pantallas

| Mensaje | Lo manda | Qué hace |
|---|---|---|
| `QUIT` (`b"salir"`) | `MaschineMK3AsPush.exe --salir`, `make stop` | cierra las pantallas en orden y termina |
| `RESTART` (`b"reiniciar"`) | el script con SHIFT + MACRO | reinicia las pantallas (ignora un segundo pedido en 5 s) |

El supervisor también usa este puerto para ser instancia única: si ya está ocupado, hay otro corriendo y el nuevo se cierra.
