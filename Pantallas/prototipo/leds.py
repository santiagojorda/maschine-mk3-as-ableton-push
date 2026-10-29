"""Apaga todas las luces de la Maschine (pads, botones y tira táctil), para el reposo.

El script de Ableton lo hace al entrar en reposo y al cerrarse, pero con Ableton cerrado o si el script no se
recargó, esas luces quedan como estaban. Entonces lo hace este programa, escribiendo al mismo puerto MIDI
(Windows MIDI Services deja que varios programas lo abran a la vez). Solo se usa en reposo: en modo DJ las
luces son de VirtualDJ y en modo Ableton, del script.
"""

import time

import mido

PAD_NOTES = range(60, 76)  # notas de los 16 pads (canal 1)
BUTTON_NOTES = range(4)  # botones 1-4 sobre las pantallas (canal 2)
# Solo los controles que son luces. Mandarle algo a los 128 también toca los mensajes especiales de MIDI
# (CC 120-127, RPN / NRPN, bank select...) y puede dejar a la Maschine en un estado raro
BUTTON_CCS = (34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 47, 48, 49, 52, 53, 55, 56, 57, 58, 59, 80, 81, 82, 83, 84, 87, 88, 100, 101, 102, 103, 104, 105, 106, 107, 110, 111)
GAP_SECONDS = 0.0005  # la Maschine pierde luces si se le manda todo de golpe


def blank_leds(port_hint):
    """Manda "apagado" a todas las luces. Devuelve cuántos mensajes mandó, o 0 si no encontró el puerto."""
    names = [name for name in mido.get_output_names() if port_hint.lower() in name.lower()]
    if not names:
        return 0
    messages = [mido.Message("note_on", channel=0, note=note, velocity=0) for note in PAD_NOTES]
    messages += [mido.Message("note_on", channel=1, note=note, velocity=0) for note in BUTTON_NOTES]
    messages += [mido.Message("control_change", channel=1, control=cc, value=0) for cc in BUTTON_CCS]
    messages.append(mido.Message("pitchwheel", channel=0, pitch=-8192))  # tira táctil
    with mido.open_output(names[0]) as port:
        for message in messages:
            port.send(message)
            time.sleep(GAP_SECONDS)
    return len(messages)
