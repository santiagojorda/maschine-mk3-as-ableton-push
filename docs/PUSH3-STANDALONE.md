# La Maschine MK3 como único controlador de un Push 3 standalone

**Estado:** idea, sin implementar. Este documento sale de leer la documentación de
[ableton-push-hack](https://github.com/federico-pepe/ableton-push-hack) y del código de este proyecto. **Nada se
probó en un Push 3.** Cada afirmación dice si está confirmada por esa documentación o si hay que verificarla.

## 1. La idea

Hoy la Maschine MK3 funciona conectada a una PC con Windows: el programa de Native Instruments convierte sus pads
y botones en MIDI, el script de Ableton (`MaschineMK3AsPush`) controla Live, y el programa de las pantallas
(`Pantallas/`) dibuja en las dos pantallas.

La idea es sacar la PC: el **Push 3 standalone** corre Live por su cuenta y la Maschine se enchufa al puerto USB-A
del Push. El Push queda como "caja" que ejecuta Live y hace el audio, y **solo la Maschine lo controla**.

```
 Maschine MK3 ──USB──► Push 3 standalone (Linux)
                         │
                         ├─ driver de la Maschine (Go) ──► puerto MIDI virtual (ALSA) ──► Live ── script MaschineMK3AsPush
                         └─ pantallas de la Maschine ◄──── driver (Go)

 Los controles del propio Push: ignorados (filtro de MIDI de push-hack)
```

Lo que **no** habría: VirtualDJ (solo corre en PC), así que no existiría el modo DJ.

## 2. Qué ya existe y se puede aprovechar

Confirmado en la documentación de push-hack (`docs/architecture.md`, `docs/push3-internals.md`, `core/README.md`):

| Dato | Detalle |
|---|---|
| Sistema | AbletonOS (Linux), kernel 5.15.48 de tiempo real, **x86_64 Intel**. Un binario de Go para `linux/amd64`, sin dependencias, corre ahí |
| Acceso | SSH (`ableton@push.local`; `root@push.local` para instalar servicios). Solo se escribe en `/data`; `/opt` es de solo lectura |
| Qué NO hay en el Push | compilador, gestor de paquetes, `libusb`, FUSE |
| MIDI | ALSA sequencer. `core/alsaseq` (Go, sin C) ya crea puertos y se conecta al "Ableton Push 3 Live Port" |
| Pantalla | `core/gfx` y `core/display` dibujan en la pantalla del Push (el hack intercepta las transferencias USB de la pantalla) |
| USB-A | el kernel trae `usbhid` como módulo, **no cargado por defecto**; push-manager tiene una casilla "USB Input" que lo carga. Un teclado enchufado ya puede controlar Live (documentado) |
| Scripts de Live | los Remote Scripts de Python se instalan en `/data/Music/Ableton/User Library/Remote Scripts/<nombre>` (el catálogo de push-hack lo hace) |
| Instalar | cada hack se publica como release en GitHub y entra al catálogo (`catalog/PUBLISHING.md`), con `hack.json` y `release.json` |
| Licencias | push-hack es MIT, ni-controllers-lib (el protocolo de la Maschine) es ISC y el script de Ableton es GPL-3.0: se pueden combinar |

## 3. Qué hay que construir

| # | Pieza | Qué es | Esfuerzo |
|---|---|---|---|
| 1 | **Acceso a la Maschine** | Leer pads y botones por `hidraw` (interfaz 4) y escribir luces. Las pantallas van por la interfaz 5 (endpoint bulk 4), y como en el Push no hay `libusb`, hay que hablar con `/dev/bus/usb` directamente desde Go. En `core/` no hay código de eso | L |
| 2 | **De HID a MIDI** | Lo que hoy hace el programa de NI: convertir pads, botones y perillas a las notas y CC que espera el script. La tabla sale de `Configuration.ncc` (es un XML) | M |
| 3 | **Puerto MIDI virtual** | Crear con `core/alsaseq` un puerto que Live vea como entrada y salida (para las luces). Hay que esperar a que pasen ~30 s del arranque antes de abrir ALSA (ver la sección 6) | S |
| 4 | **El script en el Push** | Copiar `MaschineMK3AsPush` a la carpeta de Remote Scripts del Push y activarlo como superficie de control. El catálogo habla de "un paso manual único en las Preferencias de Live" | M, con una incógnita |
| 5 | **Pantallas** | Hoy se dibujan con Python (Pillow). En el Push hay que dibujar en Go: mixer, session, browser, reposo. Es traducir la parte de dibujo | L |
| 6 | **Empaquetar** | `hack.json`, servicio en el arranque y release para el catálogo | S |

Las piezas 2, 3 y 6 son directas. La 1 y la 5 son las que llevan tiempo. La 4 tiene una incógnita (sección 7).

## 4. Que solo se controle con la Maschine

El Push tiene sus propios pads, botones y perillas, y su programa (`Push3`) los lee. Para que **no hagan nada** y la
Maschine sea la única que controla, push-hack ya trae lo necesario:

- **El filtro de MIDI** (`hacks/push-display`, el hook sobre `snd_seq_event_input`) hace que el programa del Push
  reciba un evento vacío en vez del real, mientras una señal en memoria compartida (`midiflt->enabled`) esté
  prendida. Es de todo o nada: se apagan **todos** los controles del Push.
- El hook actúa solo dentro del proceso `Push3`; Live es otro proceso. Según la documentación, el puerto virtual que
  crea push-hack para hablar con Live no pasa por ese filtro, así que Live seguiría recibiendo a la Maschine con
  normalidad. **Hay que confirmarlo** con la Maschine (fase 5).

Cómo quedaría:

1. **Al arrancar** el driver prende el filtro. Los controles del Push quedan inertes.
2. **La pantalla del Push** puede quedar con la interfaz normal de Live, o dibujar algo propio con el modo "takeover"
   del hook (por ejemplo el mismo reposo con tu nombre).
3. **Para operar lo que no se puede desde la Maschine** (Wi-Fi, actualizaciones, configuración del Push) se usa el
   teléfono (`push.local`) o SSH, como ya hace push-manager.
4. **Salida de emergencia:** con el filtro prendido el Push no responde a nada, y eso es un riesgo. Por eso el
   driver tiene que apagar el filtro solo en dos casos: si se cierra, y con una combinación de la Maschine mantenida
   unos segundos (por ejemplo SHIFT + CHANNEL + ERASE). Además queda siempre el apagado por SSH o desde push-manager.

Qué cambia al tener la Maschine como único controlador:

| Se mantiene (lo hace el script) | Se pierde |
|---|---|
| Vista session y navegar los clips | Los controles propios del Push (pads, botones y perillas sensibles al tacto) |
| Mixer, dispositivos y browser | El modo DJ y VirtualDJ |
| Tempo, volumen master y auriculares | Cualquier función que dependa de la interfaz del propio Push |
| Reposo y pantallas de la Maschine | |

Se mantiene el **audio**: sale por la interfaz del Push como siempre.

## 5. Plan por fases

Cada fase se puede probar sola y dice cuándo está lista.

| Fase | Qué | Lista cuando |
|---|---|---|
| 0 | Reconocimiento por SSH: enchufar la Maschine al Push y mirar `/sys/bus/usb/devices`. Cargar `usbhid` con push-manager | Se ve `17cc:1600` y aparece un `hidraw` para la interfaz 4 |
| 1 | Programa de Go que lee un `hidraw` e imprime los botones y pads | Cada pad y botón aparece al apretarlo |
| 2 | Escribir una imagen a una pantalla por `/dev/bus/usb` y medir la velocidad (en Windows son ~5 MB/s) | Se ve una imagen y se sabe cuántos cuadros por segundo salen |
| 3 | Puerto MIDI virtual + traducción HID→MIDI y activar el script en el Push | Un pad de la Maschine toca una nota en una pista de Live del Push |
| 4 | Pantallas: primero una imagen fija (el reposo), después el mixer y la vista session | Se ve el mixer de Live en las pantallas de la Maschine |
| 5 | Filtro de MIDI + combinación de rescate | Los controles del Push no hacen nada y la combinación los devuelve |
| 6 | Empaquetar y publicar en el catálogo | Se instala desde `push.local` sin SSH |

El orden importa: las fases 0 a 2 responden las dudas más grandes con poco trabajo. Si la 2 no anda (por ejemplo,
si la velocidad por `/dev/bus/usb` es muy baja), se sabe antes de escribir todo lo demás.

## 6. Riesgos y reglas

Todo esto sale de las advertencias de push-hack:

- **No es oficial.** Ableton no lo aprueba ni lo soporta. Se usa bajo tu propio riesgo.
- **Actualizaciones del Push:** el hack hay que **desinstalarlo antes** de actualizar el sistema del Push y volver a
  instalarlo después (el Push actualiza el firmware de su coprocesador por USB, y el hook interfiere).
- **Puerto USB-A al arrancar:** abrir ALSA durante los primeros segundos puede trabar el puerto. push-hack espera
  hasta que el equipo lleve ~30 s encendido (`WaitForBootSettle`). El driver debe hacer lo mismo.
- **No tocar `/boot` ni `/opt`.** Hacer copia de `Preferences.cfg` antes de cambiar nada en Live.
- **El firmware de la Maschine:** la interfaz 6 es la del firmware (DFU). El driver no debe abrirla.
- Con el filtro prendido, un error del driver puede dejar el Push sin respuesta hasta apagar el filtro por SSH. La
  combinación de rescate (sección 4) es obligatoria.

## 7. Qué no se sabe todavía

1. **¿Cómo se activa el script en Live del Push?** El catálogo de push-hack dice que requiere un paso manual en las
   Preferencias de Live, pero no explica cómo se llega a esas preferencias en un Push. Las opciones son editar
   `Preferences.cfg` (es binario y Live lo reescribe al cerrar) o usar un teclado y una pantalla. Hay que averiguarlo
   en la fase 3.
2. **¿La versión de Live del Push trae el marco `ableton.v3` que usa el script?** El script de chiaki lo necesita. Se
   puede ver en el Push mismo, en la carpeta de Remote Scripts de Live.
3. **¿La Maschine se ve igual conectada al Push?** Aparece como dispositivo USB compuesto, y la interfaz 4 debería ser
   un `hidraw` genérico. Si el kernel del Push reclama la interfaz 5, habría que liberarla.
4. **¿Alcanza el USB del Push para las pantallas?** Hay que medirlo (fase 2).
5. **El tiempo de CPU:** Live en el Push ya usa ~13 % en reposo. Dibujar las pantallas se suma a eso.

## 8. Veredicto

**Es viable**, y más fácil de lo que parece por todo lo que ya trae push-hack (puertos MIDI virtuales, dibujo, el
filtro de controles y el instalador). Pero **no es un cambio chico**: hay que escribir en Go el acceso USB a la Maschine
y las pantallas, y eso son varias semanas de trabajo. Lo más probable es que valga la pena empezar por las fases 0 a 2,
que se pueden hacer en un par de tardes y dicen si todo el resto es posible.

Lo que se reutiliza de este proyecto: la tabla de controles (`Configuration.ncc`), el script de Ableton tal cual, el
diseño de las pantallas, y las ideas de reposo y de cierre ordenado. Si se hace la reestructuración de la auditoría
(`docs/AUDITORIA-REFACTORIZACION.md`, en la rama `auditoria-refactor`), con dominio y puertos separados, pasar a Go
queda mucho más simple: solo habría que reescribir los adaptadores.

## Referencias

- `ableton-push-hack`: `README.md`, `docs/architecture.md`, `docs/push3-internals.md`, `core/README.md`,
  `catalog/ARCHITECTURE.md`, `catalog/schema.md`.
- Este proyecto: `Pantallas/PLAN.md` (plan del driver en Go), `docs/AUDITORIA-REFACTORIZACION.md` (rama
  `auditoria-refactor`).
