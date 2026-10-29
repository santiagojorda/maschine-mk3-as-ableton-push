# Maschine MK3 → Ableton + VirtualDJ

Contexto para retomar el trabajo. El usuario habla en español y prefiere respuestas cortas e ir de a poco.
Usa **Ableton Live 12 y VirtualDJ abiertos al mismo tiempo** con un Maschine MK3 en modo MIDI
(Windows 11 con Windows MIDI Services: los dos programas comparten el puerto del Maschine sin problema).

## Cómo funciona

- **SAMPLING** (CC 39, canal 2) pasa el Maschine a VirtualDJ: Ableton ignora todo y deja de escribir LEDs y pantalla.
- **MIXER** (CC 37) o **PLUGIN** (CC 35) lo devuelven a Ableton.
- Los dos programas reciben todos los mensajes; cada uno decide si actuar según el modo
  (Ableton con `_vdj_mode`, VirtualDJ con la variable `$vdj`).

## Dónde está cada cosa (el proyecto está repartido)

| Qué | Ruta | Nota |
|---|---|---|
| Script de Ableton **en uso** | `C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\Maschine_as_Push\` (código en `Ableton/MaschineMK3AsPush` del repo) | Repo git. Rama activa `feature/vdj-mode` (la que carga Ableton). `main` = original. `feature/knob-labels` vacía. |
| Script de Ableton original | `C:\Users\jorda\Downloads\CustomMaschineMK3-main\CustomMaschineMK3-main\CustomMaschineMK3\` | Sin modificar (fuente: github chiakibeats/CustomMaschineMK3). No editar acá. |
| Definición VirtualDJ (fuente) | `...\CustomMaschineMK3-main\VirtualDJ\Devices\MaschineMK3-VDJ.xml` | Editar acá y copiar a la instalación. |
| Mapeo VirtualDJ (fuente) | `...\CustomMaschineMK3-main\VirtualDJ\Mappers\MASCHINEMK3VDJ - Mapeo Personalizado.xml` | Ídem. |
| Instalación VirtualDJ | `C:\Users\jorda\AppData\Local\VirtualDJ\Devices\` y `\Mappers\` | Copias. Deben quedar idénticas a la fuente. |
| Plantilla del Controller Editor | `C:\Users\jorda\Documentos\Native Instruments\Controller Editor\Configuration.ncc` (XML) | Plantilla MK3 **"CUSTOM MASCHINE"**. Exportación: `Downloads\Configuration.ncc`. Backup: `Configuration.ncc.backup-2026-10-05`. |
| Generador de pads | `...\VirtualDJ\generate_pads.py` | Regenera acciones y LEDs de las 4 páginas de pads en los dos XML y valida. |
| Puente MIDI (no se usa) | `...\VirtualDJ\maschine_vdj_bridge.py` | Puerto virtual teVirtualMIDI → Maschine con log. Ver "Intentos descartados". |
| **Repositorio (GitHub, privado)** | `C:\Users\jorda\Downloads\Maschine MK3 - Presets\` → `github.com/santiagojorda/maschine-mk3-ableton-virtualdj` | Respaldo versionado de todo (README, guía HTML, este contexto, XML, script, plantilla). El script está como `git subtree` en `Ableton/CustomMaschineMK3` (traer cambios: `git subtree pull --prefix=Ableton/CustomMaschineMK3 "<repo de ProgramData>" feature/vdj-mode`). Tras cada cambio: copiar ahí, commitear y `git push`. |
| Carpeta vieja | `C:\Users\jorda\Documentos\Ableton\User Library\Remote Scripts\CustomMaschineMK3\` | Solo `__pycache__` y `settings.json`. Ableton **no** la usa. |

`...` = `C:\Users\jorda\Downloads\CustomMaschineMK3-main\CustomMaschineMK3-main`

## Flujo de trabajo

**VirtualDJ:** editar la fuente → validar → copiar a AppData.
- Validar siempre antes de copiar: el XML parsea (`xml.etree.ElementTree`) y todo `map value=` del mapeo existe como `name=` en la definición (salvo `ONINIT`). Copiar solo si valida: un mapeo roto deja el controlador muerto.
- Cambios en el **mapeo**: alcanza con desactivar/activar el Maschine en VirtualDJ. Cambios en la **definición**: hay que **reiniciar VirtualDJ**.
- Al generar acciones con Python, no usar `\"` en strings raw de reemplazo: dejó dos veces una `\` suelta al final de la acción. Chequear que el mapeo no tenga `\`.
- En comentarios XML no puede aparecer `--` (rompió el archivo una vez con `'---'`).

**Ableton:** editar en ProgramData sobre `feature/vdj-mode`, chequear sintaxis con `ast.parse`, commitear. Para recargar: reiniciar Ableton o elegir "None" y otra vez CustomMaschineMK3 en Preferences. Log: `%AppData%\Ableton\Live 12.4.6\Preferences\Log.txt`; el script escribe `CustomMaschineMK3: VirtualDJ mode = True/False` en cada cambio.

## Mapa MIDI del hardware (plantilla "CUSTOM MASCHINE", igual al script de Ableton)

Canales 0-based como en VirtualDJ (`channel="0"` = MIDI 1).
- Botones: CC en canal 1 (Plugin 35, Mixer 37, Sampling 39, Erase 54, Restart 53, Play 57, Stop 59, Left 110, Right 111, Shift por sysex `F0 00 21 09 16 00 4D 50 00 01 4D <01|00> F7`).
- Encoder grande: CC 7 canal 1 (complemento a 2); push CC 8; toque CC 9; inclinar arriba/der/abajo/izq CC 30/31/32/33.
- 8 perillas: V-Pots Mackie CC 16-23 **canal 0**, signo+magnitud (1-63 derecha, 65-127 izquierda). Toque: CC 10-17 canal 1.
- 8 botones sobre la pantalla: notas 0-7 canal 1. Grupos A-H: CC 100-107 canal 1 (LEDs: CC en canal 1 = MIDI 2, B1; la plantilla dice canal 0, pero en canal 0 no encendieron; canal 1 sin confirmar).
- Pads: notas 60-75 canal 0 (pad 1 = abajo izquierda, 16 = arriba derecha). LEDs: misma nota, la velocidad es el color.
- Colores MK3: velocidad = 4 × color + brillo (0-3). Azul 47, naranja 11, verde 31, amarillo 23.
- Touch strip: pitch bend canal 0. Sus LEDs escuchan pitch bend canal 0 en todo el rango 0-16383.
- Pantalla: protocolo Mackie, 4 líneas × 28. Header `F0 00 00 66 17 12 <pos>`, pos = línea × 28 + columna.
  **Líneas 0 y 2 = pantalla izquierda, 1 y 3 = derecha** (cada línea es de una sola pantalla).

## Ableton (`MaschineMK3AsPush.py`, antes `CustomMaschineMK3.py`, rama `feature/vdj-mode`)

- `receive_midi` y `receive_midi_chunk` filtran por `_accept_midi`. Live 12 entrega en chunks, así que hay que filtrar los dos.
- En modo VirtualDJ `build_midi_map` reenvía todo CC/nota/pitch bend de los canales 0-1 al script y lo descarta.
  Sin esto, las perillas y el strip (mapeados directo a parámetros) seguirían moviendo Live.
- `_do_send_midi` no envía nada en modo VirtualDJ.
- Al salir: `_redisplay()` reenvía las 4 líneas al instante (`DisplayLineElement.clear_send_cache()`), y `refresh_state()` corre a `VDJ_REFRESH_DELAY` = 1 tick (~100 ms) para pisar los últimos mensajes de VirtualDJ.
- SAMPLING ya no abre el editor de clips de Ableton (queda reservado).
- **SWING en Ableton = volumen de auriculares (cue)** en el encoder grande, como VOLUME con el master: componente `CueVolumeComponent` (en MasterVolumeComponent.py) sobre `master_track.mixer_device.cue_volume`, modo de encoder `swing`, pantalla "Cue Volume". Se quitó todo lo anterior de SWING (groove amount y SHIFT + SWING = position) y el Preview Volume de la perilla 1 del Browser.
- **En modo DJ pasan a Ableton:** PLAY, STOP, TAP (`ABLETON_ALWAYS_BUTTONS`, mensajes y LEDs) y el sysex de SHIFT (`SHIFT_SYSEX_PREFIX`), para SHIFT + STOP.
- **FOLLOW (CC 56)** ya no alterna Ableton Link (se saca el 10/10/2026): solo es modificador (FOLLOW + knob lanza el clip de ese track) y su LED queda apagado. En modo DJ sigue siendo el Link de VirtualDJ.
- **TEMPO (CC 47):** gira el encoder en enteros (`round(tempo) ± paso`); con SHIFT, paso fino. **SHIFT + TEMPO** iguala el tempo de Live al del deck de referencia de VirtualDJ (`vdj_master.py` lo manda por UDP a 127.0.0.1:9021) en cualquier vista, sin cambiar de vista (tampoco en modo DJ; el mapeo de VirtualDJ lo ignora). SHIFT + TEMPO ya no cambia a la escala.
- **Pads fijados en Ableton:** `Pad_Modes` pasa al modo vacío `vdj_locked` (definido en Mappings.py) para que ninguna página use los pads; al soltar se restaura el modo anterior (`_sync_pad_lock_mode`).
- **Luz de NOTES:** al apretar PITCH/MOD/PERFORM la luz de NOTES se apagaba aunque el selector de note repeat seguía activo (el script no la toca; parece el Maschine). El usuario quería lo contrario: **PITCH/MOD/PERFORM apagan NOTES** (luz y selector de note repeat), commit `38a3aa3`.
- **PERFORM + A-H = original** (cicla la asignación del crossfader A/B de cada pista, `crossfade_cycle_buttons` del Mixer). Se probaron y descartaron a pedido del usuario: botones asignables con SHIFT + PERFORM (`PerformButtonsComponent`) y pasar A-H al mapeo MIDI de Live mientras se mantiene PERFORM (`suppress_script_forwarding`). Si vuelve a pedirlo, ese segundo camino es el que distingue A de PERFORM + A.
- **Note repeat arranca en 1/16** (pedido del usuario): `NoteRepeatComponent` elige al iniciar el botón de grupo cuyo rate en Settings es `DEFAULT_REPEAT_RATE` = "1/16" (por defecto el C); antes arrancaba en el primero (A).
- **Pad lock** (`_pad_lock`, `PAD_LOCK_BUTTON` = LOCK CC 48 canal 2): LOCK en modo VirtualDJ lo alterna. Al volver a Ableton con el pad lock activo, los pads siguen siendo de VirtualDJ: el script descarta sus notas 60-75 (y las reenvía al script en `build_midi_map` para que una pista armada no suene) y no manda LEDs de pads. En Ableton, LOCK con pad lock activo solo lo suelta (se traga apretar y soltar) y redibuja; si no, LOCK hace su función normal de Ableton.

## Consistencia Ableton ↔ VirtualDJ (revisar al tocar modos, LOCK o pads)

Cada programa lleva su propio estado; tienen que moverse igual con los mismos botones.

| Evento | Ableton (`_vdj_mode`, `_pad_lock`) | VirtualDJ (`$vdj`, `$padlock`, `$pads`) |
|---|---|---|
| Arranque | F, F | 0, 0, 0 |
| SAMPLING | modo VDJ (ignora todo, no envía nada) | `$vdj`=1, `$pads`=1, key lock on; al entrar desde Ableton los pads pasan a PAD MODE (`$padpage` 1) salvo que el pad lock (`$padlock`) ya estuviera activo |
| LOCK en modo VDJ | alterna `_pad_lock` | alterna `$padlock` (LED de LOCK) |
| MIXER/PLUGIN | sale del modo; si `_pad_lock`, ignora la sección de pads y no pinta sus LEDs | `$vdj`=0, `$pads`=`$padlock` |
| LOCK en Ableton con pads fijados | suelta (se traga apretar/soltar) y redibuja | `$padlock`=0, `$pads`=0 |
| LOCK en Ableton sin fijar | función normal de Ableton | sin cambios |

- **Sección de pads** = pads (notas 60-75) + botones de página PAD MODE/KEYBOARD/CHORDS/STEP (CC 81-84). Mientras está fijada a VirtualDJ, Ableton ignora esos mensajes y no manda sus LEDs ni el de LOCK (queda prendido por VirtualDJ).
- Del lado de VirtualDJ, todo lo de la sección de pads se condiciona con `$pads`; el resto con `$vdj`.
- Reiniciar solo uno de los dos desincroniza: se recupera con MIXER/PLUGIN (sale del modo en ambos), SAMPLING (entra en ambos) y LOCK en Ableton (suelta los pads).

## VirtualDJ: lógica del mapeo

Variables: `$vdj` (modo), `$pads`, `$padlock`, `$encmode`, `$select`, `$help`, `$stem1`, `$stem2`, `$shift`, `$erase`, `$knob` (perilla tocada, 0 = ninguna), `$xf` (tramo 1-16 del crossfader), `$padpage` (0 cues / 1 transporte / 2 stems / 3 apagado), `$browse`, `$preview`. Todo se inicializa en `ONINIT`.
Todas las acciones están envueltas en `var '$vdj' ? (...) : nothing`.

- **Pads: cuatro páginas** (`$padpage`). **KEYBOARD** (CC 82) = 0 = hot cues; **PAD MODE** (CC 81) = 1 = transporte; **CHORDS** (CC 83) = 2 = stems; **STEP** (CC 84) = 3 = todos los pads apagados y sin función. Columnas 1-2 = deck 1, columnas 3-4 = deck 2.
  Cues 1-8 de arriba hacia abajo, izquierda a derecha; ERASE + pad = borrar; LED azul (D1) o naranja (D2) si hay cue.
  Transporte por deck, de abajo hacia arriba: PLAY verde | PAUSA rojo, (vacío) | SYNC amarillo (arriba de PAUSA, pads 6 y 8; INICIO se sacó a pedido del usuario) — luz fuerte en **los dos** pads SYNC cuando los decks están sincronizados: `match_bpm` (mismo BPM, queda fijo) o `is_sync` de cualquiera de los dos. Según el foro de VirtualDJ, `is_sync` = BPM **y fase** mientras suena (BPM solo si está parado), así que solo con `is_sync` el pad se prendía y apagaba al correrse la fase; y la consulta `sync` titila con la intensidad del beat (**no usarla**). La pantalla usa lo mismo por deck: `match_bpm ? SYNC : is_sync ? SYNC : NO SYNC` (MASTER tiene prioridad), LOOP 4 violeta | PITCH LOCK naranja (`pitch_lock` = el candado de VirtualDJ; el usuario quiere que solo active/desactive el candado), LOOP ½ | LOOP ×2 celeste (el usuario quiere PLAY/PAUSA en la fila de abajo). Tenue siempre, fuerte cuando está activo.
  Stems por deck: columna derecha, de arriba hacia abajo; en la izquierda solo HATS (abajo, al lado de KICK). **Pads independientes, puede haber varios prendidos** (pedido del usuario): RESET amarillo = prende todo, fuerte si suenan todos; INSTRUMENTAL azul = alterna Instru y Bass juntos (si suenan los dos los apaga, si no los prende), fuerte si suenan Instru y Bass; VOZ verde (antes ACAPELLA) = alterna solo la voz, fuerte si suena la voz; KICK rojo (antes DRUMLESS) = alterna solo el kick, fuerte si suena el kick (el usuario lo quiere así); HATS naranja = alterna solo el hihat, fuerte si suena. Después de RESET quedan prendidos los cuatro. Se usa **`stem_pad 'vocal'|'instru'|'bass'|'kick'|'hihat'`** (lo mismo que la página de stems propia de VirtualDJ, con `autodim="query"`): como consulta es true mientras el stem **suena**, como acción alterna el mute. Con `mute_stem` como consulta DRUMLESS sacaba la voz (semántica dudosa), así que no se usa `mute_stem` ni `only_stem`. Para fijar un stem se lo toca solo si hace falta (`set_mute` en `generate_pads.py`). VirtualDJ también tiene `stem_pad 'acapella'` / `'instrumental'` (grupos). `DECK` se expande a `deck n`.
  **Toda la sección de pads (acciones + LEDs) y el modo info se generan con `VirtualDJ/generate_pads.py`**: editar `TRANSPORT`/`STEMS`/`HELP_BUTTONS` ahí y correrlo, no a mano. Si se agrega un botón nuevo al mapeo, sumarlo a `HELP_BUTTONS`. **Después de correrlo, instalar los DOS XML (Devices y Mappers)**: si cambia un color, el elemento LED nuevo está en la definición, y con solo el mapeo el pad queda sin esa luz.
  LEDs de pads: un `<sysex>` por (pad, color) llamado `LED_P<pad>_<color hex>`, cuya condición es verdadera solo en ese estado y página. Las luces de KEYBOARD/PAD MODE/CHORDS (CC canal 2) marcan la página.
- **Perillas:** 1 = jog deck 1, 2 = jog deck 2 (`jogwheel ±0.05` por paso; SHIFT = `goto ±16`, 4 compases; ERASE + tocar = `deck n pitch_reset`, vuelve suave al tempo original). 3 = tempo D1, 4 = tempo D2 (`pitch +1 bpm` / `pitch -1 bpm` por paso, sintaxis con espacio según el foro de VirtualDJ; al tocarlas, pantalla izquierda "TEMPO Dn" arriba y abajo el BPM entero + "ORIGINAL" + `get_bpm absolute` (BPM original del tema, sin pitch; documentado en el manual de VDJScript); ERASE + tocar = `deck n pitch_reset`, vuelve suave al tempo original del tema; antes había un `repeat_start` gradual que no llegaba bien). 5 = volumen D1, 6 = volumen D2, 7 = filtro D1, 8 = filtro D2 (2% por paso; ERASE + tocar = filtro al centro, volumen al 100%). El kick se sacó.
- **Tocar una perilla de mezcla:** la pantalla depende de la **posición** de la perilla (1-4 izquierda, 5-8 derecha), no del deck: arriba `VOLUMEN D1` / `FILTRO D2`…, abajo el valor (filtro −50%..+50%, volumen 0-100%, como texto). Tocar un jog: pantalla izquierda "MOVIENDO JOG" arriba y "DECK 1/2" abajo ($knob 1/2).
- **Encoder grande:** girar = `browser_scroll` en la zona activa. Apretar = `browser_window 'folders,songs'` (como la DDJ-400). Inclinar arriba/abajo = scroll ±1. Inclinar a los costados: en carpetas abre/cierra la carpeta, en temas carga en deck 1/2. SHIFT + costado = `clone_from_deck` (copia el tema que suena en el otro deck, misma posición). Ojo: dos `load` seguidos rápido hacen el "instant double" nativo de VirtualDJ (igual que la DDJ-400).
- **Pads siguen a `$pads`** (= modo VirtualDJ o pad lock). SAMPLING → `$pads` 1; MIXER/PLUGIN → `$pads` = `$padlock`. LOCK en modo VirtualDJ alterna `$padlock` (LED de LOCK); en Ableton lo pone en 0. Debe coincidir con `_pad_lock` del script de Ableton (si uno se reinicia solo, quedan desfasados).
- **Stem tocado en pantalla:** al tocar un pad de stems, la pantalla de su deck muestra el nombre arriba y ON/OFF abajo (RESET: "TODOS ON") durante `STEM_DISPLAY_TIME` (1,5 s), con `$stem1`/`$stem2` y un temporizador `repeat_start 'stemN' 1500ms 1 & set '$stemN' 0` (se usa temporizador porque detectar soltar un pad no es confiable). Lo genera `generate_pads.py`.
- **SELECT = modo info** (CC 90, slider; solo en modo VirtualDJ, `$select`): mientras se mantiene, tocar un pad o un botón de `HELP_BUTTONS` no hace su acción, guarda un código en `$help` y la pantalla izquierda muestra su nombre arriba (abajo vacía). Nombres sin deck (el usuario no quiere D1/D2). Todo lo genera `generate_pads.py` (envuelve las acciones con `var '$select' 1 ? (set '$help' N) : (...)`; correrlo de nuevo no duplica). SAMPLING/MIXER/PLUGIN quedan afuera porque Ableton también los escucha; MIXER/PLUGIN ponen `$select` en 0.
- **VOLUME (CC 44) / SWING (CC 45) = modos del encoder grande** (`$encmode`: 0 lista, 1 volumen master, 2 volumen de auriculares; se excluyen, apretar de nuevo vuelve a 0). Girar = `master_volume` / `headphone_volume` ±2%. Mientras el modo está activo, la pantalla izquierda muestra "VOLUMEN MASTER" / "VOLUMEN AURIS" y el %. LEDs de VOLUME / SWING. **Compartido con Ableton:** VirtualDJ registra VOLUME/SWING también fuera del modo DJ (TEMPO en cualquier modo pone `$encmode` 0: VOLUME/SWING/TEMPO exclusivos) y el script de Ableton deja pasar VOLUME/SWING/TEMPO en modo DJ (`SHARED_ENCODER_MODE_BUTTONS`, sin LEDs), así el modo queda igual al cambiar. Textos iguales en los dos: "VOLUMEN MASTER" / "VOLUMEN AURIS". En Ableton, VOLUME/SWING/TEMPO **tienen prioridad sobre las vistas Browser y Settings** (`EncoderModeControlComponent`, commit `9392cd2`): toman el encoder en cualquier vista y al apretar de nuevo vuelve al de la vista (`_view_encoder_mode`). **Cambiar de vista los apaga** (pedido del usuario): `reset_selected_mode` al cambiar `Display_Modes` y al apretar CHANNEL/PLUGIN/MIXER/BROWSER/SETTINGS (`VIEW_BUTTONS`, también si la vista no cambia); en VirtualDJ esos botones ponen `$encmode` 0 (CHANNEL/BROWSER/SETTING solo fuera del modo DJ, MIXER/PLUGIN siempre); antes el script original los ignoraba ahí y se desincronizaba con VirtualDJ. Mientras el modo está activo, la pantalla izquierda lo muestra sin tocar el encoder y **la derecha queda vacía** (pedido del usuario; Ableton: líneas 1 y 3 vacías; VirtualDJ: `$encmode` ≠ 0 → `' '` en LCD_TITLE_D2 / LCD_BOTTOM_D2) (`knob_control_view` en DisplayDefinitions.py; una perilla tocada tiene prioridad), igual que VirtualDJ con `$encmode`. Capa de pantalla: SELECT > stem > `$encmode` > browser > perillas > normal. Con `$encmode` ≠ 0 el toque/clic del encoder no activa `$browse` (si no, la pantalla derecha quedaba en blanco al girar).
- **Key lock (el tono no cambia con el tempo) siempre activo:** `deck n key_lock ? nothing : deck n key_lock` (`key_lock on` parecía alternar) en ONINIT, al apretar SAMPLING y en cada paso de las perillas de tempo 3-4. **No es el pad PITCH LOCK**: ese pad es el candado (`pitch_lock`, verbo distinto; `key_lock` y `pitch_lock` existen los dos en VirtualDJ).
- **Transporte:** PLAY, STOP y SHIFT + STOP son **de Ableton también en modo DJ** (el script de Ableton los deja pasar con el sysex de SHIFT; VirtualDJ no los mapea). RESTART = goto_start del deck elegido con LEFT/RIGHT (el usuario sacó el pad INICIO, no este botón).
- **FOLLOW en modo DJ = Ableton Link de VirtualDJ:** `deck master effect_active 'Ableton Link'`, LED de FOLLOW (B1 38). En Ableton, FOLLOW alterna el Link de Ableton (lo maneja el script de Ableton solo fuera del modo DJ).
- **TAP es siempre de Ableton** (tap tempo; SHIFT + TAP = metrónomo): VirtualDJ no lo mapea y el script de Ableton lo deja pasar en modo DJ.
- **Browser en pantalla:** mientras se toca el encoder grande (CC 9) **y** el foco está en la lista de temas (`$browse`; se recalcula al tocar y al apretar el encoder): izquierda arriba `get_browsed_song 'title'`, abajo `'artist'`; derecha arriba vacía, abajo `get_browsed_song 'bpm'`. Sin desplazamiento. En la vista de carpetas (`$browse` = 2) solo se muestra `get_browsed_folder` arriba a la izquierda; el resto en blanco.
- **NOTES (CC 52) = preescucha tipo gate:** `prelisten on` al apretar, `prelisten_stop` al soltar (definido como slider). Con `prelisten` a secas no sonaba: probablemente tomaba el valor del slider (1.0) como posición = final del tema. (Antes estaba en PITCH; el usuario la movió a NOTES. PITCH quedó sin uso.)
- **Luces de MIXER y PLUGIN en modo DJ:** VirtualDJ las apaga al entrar (`LEDOFF_MIXER` / `LEDOFF_PLUGIN` = `var '$vdj'`), porque Ableton deja de mandar luces y quedaban prendidas; al volver, el script de Ableton las repinta.
- **Efectos y preescucha:** VirtualDJ está en `fxProcessing = Pre-fader` (tema → efectos → EQ/filtro → volumen). Probado por el usuario: con *Post-fader* los efectos **no se escuchan en los auriculares** (PFL), así que se deja Pre-fader. `equalizerInHeadphones = yes`.
- **Touch strip:** crossfader. Al moverlo, la pantalla izquierda muestra "CROSSFADER" y la posición (−50% deck 1 … +50% deck 2) 1,5 s (`$knob` 9 + temporizador `xfshow` **al final** de la acción: `repeat_start` repite todo lo que viene después). Sus LEDs muestran el tramo guardado en `$xf`.
- **Grupos A-H (CC 100-107):** A C E G = deck 1 (LED azul), B D F H = deck 2 (LED naranja). A/B Reverb, C/D Flanger, E/F Echo (`effect_active 'Nombre'`), G/H preescucha (`pfl`). LED solo cuando está activo. Echo Out se probó y no le gustó al usuario.
- **Botones sobre la pantalla (notas 0-7, canal 1):** los **1-4 (MAICOL, SESSION, EN, TU ♥) son solo de VirtualDJ** (pedido del usuario), en los dos modos (sin `$vdj`): **1 y 3 = DRUMLESS** del deck 1 / 2 (alterna kick + hihat silenciados) y **2 y 4 = BATERIA** (deja solo kick + hihat; otra vez = todo). Luz `91 nn 7F` prendida mientras el modo está activo; pantalla del deck con nombre y ON/OFF ($stemN 21 / 22). Los genera `generate_pads.py` (`STEM_BUTTONS`). El script de Ableton los ignora siempre, entrada y luces (`_is_vdj_only`, commit `2dc2138`). Los 5-8 siguen siendo de Ableton (asignaciones MIDI propias del usuario). Ojo: una asignación MIDI manual de Live sobre 1-4 no la puede bloquear el script; hay que borrarla en Ableton.
- **Pantallas:** izquierda deck 1, derecha deck 2; un campo de 27 caracteres + `0x00` fijo por línea, `scroll="false"`. Arriba el título (o "DECK n"). Abajo `get_text` combinando con comillas invertidas: "`` `deck n get_bpm & param_cast 'text' 6` `` + 8 espacios + MASTER/SYNC/NO SYNC" (`---` si está vacío). Fuera del modo se manda `''` para forzar el redibujado al volver. **Error de carga** (`deck n deck_has_error`): arriba el título (`get_title`) y abajo "Error al cargar!" (pedido así por el usuario).
- **Largo del loop en pantalla:** LOOP ½ y LOOP ×2 (pads 13-16 de PAD MODE) ponen `$stemN` = `LOOP_DISPLAY_CODE` (20) 1,5 s: arriba "LOOP", abajo `get_loop` (tiempos) + "BEATS". Lo genera `generate_pads.py` (`LOOP_DISPLAY_NAMES`), con la misma capa y temporizador que los stems.

## Lecciones (comportamientos de VirtualDJ que costaron)

1. **El valor implícito de un encoder o slider se pierde dentro de una condición** (`var ? (browser_scroll) : ...`). Usar `param_greater 0 ? X +1 : X -1`. El crossfader con `(crossfader)` sí anduvo.
2. **`down ? a : b` funcionó al revés** en botones CC. Para controles de "mantener" (ERASE, toque de perillas) se definen como `<slider>` y se usa `param_bigger 0.5 ? apretado : soltado`.
3. **Los `<led note|cc ...>` nunca encendieron.** Las luces se mandan como `<sysex value="903C2F">` crudo (sirve para cualquier MIDI, no solo sysex), con un elemento ON y otro OFF por LED. El elemento se envía cuando su acción pasa a verdadera.
4. **`get_text` acepta comillas invertidas** para insertar resultados (`get_text "BPM `get_bpm`"`); dentro del atributo XML las comillas dobles van como `&quot;`.
4b. **Textos numéricos en `<text>`:** parece que VirtualDJ solo reenvía un número cuando el número cambia, así que el BPM no volvía tras pisarlo. Se mandó como texto (`param_cast 'text' 6`). El campo del BPM usa la misma cadena `var '$knob' N ? valor : ...` que ya funcionaba bien en el campo del SYNC (el usuario prefiere el valor de la perilla en el lugar del BPM).
5. Los botones CC necesitan `value="0x7F" off="0x00"` en la definición.
6. **Elementos `<slider>`:** VirtualDJ le pasa su valor al comando si este no tiene parámetro. Darle siempre un parámetro explícito (`prelisten on`, `set '$x' 1`).
6b. **Comillas invertidas en acciones no funcionan** (probado: ``pitch `get_bpm & ...` bpm`` no hace nada). Solo sirven dentro de `get_text`. No se puede calcular un BPM entero de destino.
7. Las expresiones muy largas o con condiciones anidadas dentro de `&` dejaron de evaluar. Mantenerlas simples.
8. **Acentos:** Windows MIDI descarta los bytes > 0x7F en el camino (probado: "Rebelión" llega como "Rebelin"). Con `encoding="ascii"` VirtualDJ manda "?". No hay solución.
9. **Nombres de botones/perillas en pantalla** ("V-Pot 1", nombres de los botones 1-8): son fijos de la plantilla. El Controller Editor no relee `Configuration.ncc` en vivo (probado).
10. **Alineación de líneas (resuelto):** el Maschine centra cada línea según su largo sin contar los espacios finales. Solución confirmada: cada `<text>` tiene 27 caracteres de texto y un `0x00` fijo en la columna 28 (en la plantilla del sysex), así ninguna línea termina en espacio y todas quedan alineadas a la izquierda; el `0x00` no se ve.
11. **Imágenes en las pantallas:** no se puede por MIDI. Requiere el protocolo NIHIA de Native Instruments (ver github mo0kid/maschine-md-mm, solo macOS) y probablemente choca con el modo MIDI.

12. **Un botón que deja de mandar MIDI (pasó con CHORDS, 2026-10-05; probado: no tiene que ver con las luces de los botones 1-4, el botón físico falla a veces):** el Controller Editor lo veía y la plantilla estaba bien, pero no salía nada por el puerto (ni VirtualDJ ni Ableton lo recibían; se diagnosticó con un monitor MIDI de solo lectura sobre "Maschine MK3 Ctrl MIDI", winmm). Volvió a andar tras reconectar el Maschine / reasignar el botón en el Controller Editor / reiniciar. No era del mapeo. En Ableton CHORDS = modo de velocidad fija y sigue sin responder; al usuario no le importa.

## Intentos descartados

- **Puente** (`maschine_vdj_bridge.py`, VirtualDJ → puerto virtual "Maschine VDJ Out" → Maschine): con `drivernameout` apuntando ahí, VirtualDJ no mandó nada al puerto y siguió usando la definición anterior. Se volvió a salida directa. El script funciona (probado aparte) por si hace falta loguear.
- **Plantilla con otro canal para VirtualDJ:** evaluada y descartada. La pantalla Mackie no tiene canal y Ableton la seguiría pisando.

## Estado y pendientes (al 2026-10-05)

Confirmado por el usuario: modo SAMPLING/MIXER/PLUGIN, encoder/browser, crossfader y sus LEDs, ERASE + pad, guardar cues, nombre de la perilla al tocarla, LEDs por sysex crudo (pads, grupos, SAMPLING), alineación de pantallas, ±1 BPM en las perillas 3-4.

**Sin confirmar con el equipo** (últimos cambios; requieren reiniciar VirtualDJ y recargar el script de Ableton):
- Stems con `stem_pad` (RESET / INSTRUMENTAL / VOZ / KICK / HATS independientes) y sus luces.
- PITCH LOCK = `pitch_lock` (candado) y key lock forzado en las perillas de tempo.
- ERASE + perilla 1-4 = `pitch_reset`.
- Luz del pad SYNC y SYNC / NO SYNC en pantalla con la consulta `sync`.
- VOLUME / SWING / TEMPO exclusivos y compartidos (commits `228dddb`, `658309f`).
- SHIFT en VirtualDJ (sysex `sysexin`): nunca se confirmó; si SHIFT + jog no salta, VirtualDJ no recibe el SHIFT.
- "El pitch se mueve solo": probablemente Ableton Link o SYNC activo.

## Touch strip en modo PITCH (Ableton)
**No tocar el forwarding del touch strip.** Se probó que las luces siguieran el dedo pasando `pitchbend_encoder` a `MODE_PLAYABLE_LISTENABLE` (ScriptForwarding.non_consuming) y reenviando cada `E0` a las luces: el script recibía el pitch bend pero **Ableton dejaba de pasárselo a la pista** y el pitch dejó de sonar (diagnosticado con un log temporal, el usuario confirmó que en el original siempre anduvo). Se revirtió (commit `bc0a6cb`): queda como el original (`MODE_PLAYABLE` = ScriptForwarding.none, el pitch bend va directo a la pista) y el script no toca las luces del strip en PITCH.
**Espejo en VirtualDJ:** como VirtualDJ también recibe el touch strip estando en Ableton, prende las 16 luces (`XF_LED_n` con `$ps`) mientras Ableton está en PITCH y las centra al soltar (`TOUCHSTRIP_RELEASE` = pitch bend canal 2 → `$ps` 0 → `STRIP_LED_CENTER` `E0 00 40`). `$abstrip` sigue el modo del strip de Ableton con PITCH/MOD/PERFORM (CC 49/50/51) fuera del modo DJ (1/2/3; ONINIT = 1). Necesita VirtualDJ abierto. Sin confirmar con el equipo.

- **SCENE + click del encoder** lanza la escena del cursor (`song.view.selected_scene.fire()`), en cualquier vista de Ableton. **PATTERN** (CC 86) ya no es el "fixed length" ni cambia la resolucion del STEP con los botones de grupo: ahora captura los clips que suenan en una escena nueva (`song.capture_and_insert_scene()`, como Push).
- **LOCK (pads fijados a VirtualDJ) tambien fija el touch strip (crossfader) y los botones A-H:** en Ableton con LOCK puesto, el script los descarta (`_is_pad_section`, y no les escribe LEDs) y el mapeo de VirtualDJ los atiende con `$pads` (modo DJ o LOCK) en vez de `$vdj`. Sin LOCK, son de Ableton como siempre.
