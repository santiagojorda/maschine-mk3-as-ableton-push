"""Construye docs/index.html y docs/all-operations.html a partir de Custom Maschine - All Operations.html,
incorporando las imágenes de las pantallas de Ableton y branding 100% enfocado en Ableton Push.
"""

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'docs', 'all-operations.html')
DEST_INDEX = os.path.join(ROOT, 'docs', 'index.html')
DEST_ALL = os.path.join(ROOT, 'docs', 'all-operations.html')

with open(SRC, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Títulos y branding
html = html.replace('Maschine MK3 · Ableton + VirtualDJ', 'Maschine MK3 as Ableton Push')
html = html.replace('Maschine MK3: Ableton + VirtualDJ', 'Maschine MK3 as Ableton Push')
html = html.replace(
    '<h1>Maschine MK3: Ableton + VirtualDJ</h1>',
    '<h1>Maschine MK3 as Ableton Push</h1>'
)
html = html.replace(
    'Guía de uso del Maschine MK3 con Ableton Live 12 y VirtualDJ (script MaschineMK3AsPush modificado).',
    'Guía interactiva completa de todas las operaciones para Maschine MK3 como Ableton Push en Live 12.'
)

# 2. Eliminar el bloque mm-box completo (sección residual de VirtualDJ)
html = re.sub(r'<div class="mm-box">.*?</div>\s*(?=<p>Todas las funciones|<h2)', '', html, flags=re.DOTALL)

# 3. Limpiar el Table of Contents de la derecha
html = re.sub(
    r'<li><a href="#mi-maschine"[^>]*><b>Mi Maschine: Ableton \+ VirtualDJ</b></a><ul>.*?</ul></li>',
    '',
    html,
    flags=re.DOTALL
)
html = re.sub(r'<li><a href="#ableton"[^>]*><b>Ableton: todas las funciones</b></a></li>', '', html)

# 4. Limpiar notas residuales en tablas
html = re.sub(r'<span class="mm-note">Si los pads están fijados a VirtualDJ.*?</span>', '', html)
html = re.sub(r'<span class="mm-note">En mi setup, SAMPLING pasa el Maschine a VirtualDJ.*?</span>', '', html)
html = re.sub(r'<span class="mm-note">Ya no: SAMPLING ahora pasa el Maschine a VirtualDJ.*?</span>', '', html)
html = re.sub(r'<span class="mm-note">Sigue funcionando en modo VirtualDJ.*?</span>', '', html)
html = re.sub(r'<span class="mm-note">Ya no: FOLLOW ahora activa/desactiva Ableton Link.*?</span>', '', html)
html = re.sub(r'<p>Todas las funciones del script en Ableton \(en inglés\)\..*?</p>', '<p>Todas las funciones y combinaciones de controles del script para Ableton Live 12.</p>', html)

# 5. Insertar Hero Image y badges justo debajo de <header><h1>Maschine MK3 as Ableton Push</h1></header>
hero_block = '''<header><h1>Maschine MK3 as Ableton Push</h1></header>
<div class="mm-hero-card" style="margin: 1.5rem 0 2rem; text-align: center; background: var(--ifm-color-emphasis-100); padding: 1.5rem; border-radius: 12px; border: 1px solid var(--ifm-color-emphasis-300);">
  <img src="images/maschine-mk3-as-push-standby.png" alt="Maschine MK3 as Ableton Push by @santiagojorda" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 24px rgba(0,0,0,0.25); display: inline-block;">
  <div style="display: flex; justify-content: center; flex-wrap: wrap; gap: 8px; margin-top: 1.25rem;">
    <a href="https://github.com/santiagojorda/maschine-mk3-as-ableton-push" target="_blank"><img src="https://img.shields.io/badge/GitHub-Repositorio-black?logo=github&style=flat-square" alt="GitHub"></a>
    <a href="https://www.youtube.com/watch?v=ImqHw-zkiZQ&list=PLxk2dEOPjuEYO00P264yMStEUhukVkO1y" target="_blank"><img src="https://img.shields.io/badge/YouTube-Maicol%20Session-FF0000?logo=youtube&logoColor=white&style=flat-square" alt="YouTube"></a>
    <a href="http://instagram.com/santiagojorda" target="_blank"><img src="https://img.shields.io/badge/Instagram-@santiagojorda-E4405F?logo=instagram&logoColor=white&style=flat-square" alt="Instagram"></a>
    <img src="https://img.shields.io/badge/Ableton%20Live-12%20Suite-00D2B4.svg?style=flat-square" alt="Ableton Live 12">
    <img src="https://img.shields.io/badge/Hardware-Maschine%20MK3-black.svg?style=flat-square" alt="Maschine MK3">
  </div>
  <p style="margin-top: 1rem; margin-bottom: 0; font-size: 1.05em; color: var(--ifm-color-emphasis-800);">
    Convertí tu <strong>Maschine MK3</strong> en un controlador estilo <strong>Ableton Push</strong> para Live 12: pantallas a color en vivo, mixer gráfico, control de dispositivos y navegación total sin tocar el mouse.
  </p>
</div>'''

html = html.replace('<header><h1>Maschine MK3 as Ableton Push</h1></header>', hero_block)

# 6. Insertar imagen de Session View
session_img_block = '''<h2 class="anchor anchorWithStickyNavbar_LWe7" id="session-view">Session View<a href="#session-view" class="hash-link" aria-label="Direct link to Session View" title="Direct link to Session View">&#8203;</a></h2>
<div style="margin: 1.25rem 0 1.75rem; text-align: center;">
  <img src="images/ableton-session-view.png" alt="Vista Session en las pantallas" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 18px rgba(0,0,0,0.2);">
  <p style="font-size: 0.9em; color: var(--ifm-color-emphasis-700); margin-top: 0.5rem;"><strong>Pantallas en Vista Session:</strong> Grilla completa de 8 pistas &times; 4 escenas con nombres, colores reales de clips, borde verde de reproducción y cursor activo.</p>
</div>'''

html = re.sub(
    r'<h2 class="anchor anchorWithStickyNavbar_LWe7" id="session-view">Session View.*?</h2>',
    session_img_block,
    html,
    count=1
)

# 7. Insertar imagen de Mixer View
mixer_img_block = '''<h2 class="anchor anchorWithStickyNavbar_LWe7" id="mixer">Mixer<a href="#mixer" class="hash-link" aria-label="Direct link to Mixer" title="Direct link to Mixer">&#8203;</a></h2>
<div style="margin: 1.25rem 0 1.75rem; text-align: center;">
  <img src="images/ableton-mixer-view.png" alt="Vista Mixer en las pantallas" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 18px rgba(0,0,0,0.2);">
  <p style="font-size: 0.9em; color: var(--ifm-color-emphasis-700); margin-top: 0.5rem;"><strong>Pantallas en Vista Mixer:</strong> Faders verticales por canal, v&uacute;metros graduados en dB, paneo est&eacute;reo y marco verde de asignaci&oacute;n a pads.</p>
</div>'''

html = re.sub(
    r'<h2 class="anchor anchorWithStickyNavbar_LWe7" id="mixer">Mixer.*?</h2>',
    mixer_img_block,
    html,
    count=1
)

# 8. Insertar imagen de Device Control View
device_img_block = '''<h2 class="anchor anchorWithStickyNavbar_LWe7" id="device-control">Device Control<a href="#device-control" class="hash-link" aria-label="Direct link to Device Control" title="Direct link to Device Control">&#8203;</a></h2>
<div style="margin: 1.25rem 0 1.75rem; text-align: center;">
  <img src="images/ableton-device-view.png" alt="Vista Dispositivo en las pantallas" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 18px rgba(0,0,0,0.2);">
  <p style="font-size: 0.9em; color: var(--ifm-color-emphasis-700); margin-top: 0.5rem;"><strong>Pantallas en Vista Dispositivo / Plugins:</strong> Las 8 perillas toman los par&aacute;metros del instrumento o efecto con nombres y valores en tiempo real.</p>
</div>'''

html = re.sub(
    r'<h2 class="anchor anchorWithStickyNavbar_LWe7" id="device-control">Device Control.*?</h2>',
    device_img_block,
    html,
    count=1
)

# 9. Insertar imagen de Browser View
browser_img_block = '''<h2 class="anchor anchorWithStickyNavbar_LWe7" id="browser">Browser<a href="#browser" class="hash-link" aria-label="Direct link to Browser" title="Direct link to Browser">&#8203;</a></h2>
<div style="margin: 1.25rem 0 1.75rem; text-align: center;">
  <img src="images/ableton-browser-view.png" alt="Vista Browser en las pantallas" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 18px rgba(0,0,0,0.2);">
  <p style="font-size: 0.9em; color: var(--ifm-color-emphasis-700); margin-top: 0.5rem;"><strong>Pantallas en Vista Browser:</strong> Navegador de sonidos a la derecha (User Library, carpetas, presets) y grilla de destino a la izquierda.</p>
</div>'''

html = re.sub(
    r'<h2 class="anchor anchorWithStickyNavbar_LWe7" id="browser">Browser.*?</h2>',
    browser_img_block,
    html,
    count=1
)

# 10. Pie de página
html = html.replace('Guía de uso local · actualizada el 5 de octubre de 2026', 'Maschine MK3 as Ableton Push · Manual de Operaciones')

# Verificación de VirtualDJ
rem = re.findall(r'.{0,40}(?:virtualdj|virtual dj|vdj).{0,40}', html, re.IGNORECASE)
print(f'Menciones restantes de VirtualDJ: {len(rem)}')
for r in rem:
    print(' ', r)

# Guardar en docs/index.html y docs/all-operations.html
with open(DEST_INDEX, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Generado: {DEST_INDEX}')

with open(DEST_ALL, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Generado: {DEST_ALL}')
