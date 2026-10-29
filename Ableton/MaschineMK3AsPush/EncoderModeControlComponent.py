# ==================================================
#
# This file is part of Maschine MK3 as Push, based on CustomMaschineMK3 by chiaki.
# Maschine MK3 as Push is free software licensed under GPL-3.0.
# For more details, see "LICENSE" file.
# 
# Copyright (C) 2024-2025 chiaki
# Copyright (C) 2026 Santiago Jorda
#
# ==================================================

from ableton.v3.control_surface.component import Component
from ableton.v3.control_surface.controls import ButtonControl
from ableton.v3.control_surface.mode import pop_last_mode
from ableton.v3.base import listens

from .Logger import logger

class EncoderModeControlComponent(Component):
    volume_button = ButtonControl(color = "DefaultButton.Off", on_color = "DefaultButton.On")
    swing_button = ButtonControl(color = "DefaultButton.Off", on_color = "DefaultButton.On")
    tempo_button = ButtonControl(color = "DefaultButton.Off", on_color = "DefaultButton.On")
    shift_button = ButtonControl(color = None)

    volume_modes = ("volume",)
    # SWING only switches the encoder to the cue (headphones) volume, like VOLUME with the master volume
    swing_modes = ("swing",)
    # TEMPO is only the tempo (SHIFT + TEMPO used to switch the encoder to the scale selector)
    tempo_modes = ("tempo",)

    _encoder_modes = None
    _display_modes = None
    _selected_encoder_mode = None

    def __init__(self, name = "Encoder_Mode_Control", *a, **k):
        super().__init__(name, *a, **k)

    @volume_button.pressed
    def _on_volume_button_pressed(self, button):
        self._handle_mode_button_pressed(self.volume_modes)

    @swing_button.pressed
    def _on_swing_button_pressed(self, button):
        self._handle_mode_button_pressed(self.swing_modes)

    @tempo_button.pressed
    def _on_tempo_button_pressed(self, button):
        self._handle_mode_button_pressed(self.tempo_modes)

    def _handle_mode_button_pressed(self, modes):
        if self._encoder_modes == None:
            return
        
        selected_mode = self._encoder_modes.selected_mode
        # VOLUME / SWING / TEMPO take over the encoder in every view, browser and settings included (like VirtualDJ),
        # so both programs always agree on the selected mode. Pressing again gives the encoder back to the view.
        shift = self.shift_button.is_pressed
        if len(modes) > 1:
            # If a mode button has two modes and press mode button with shift when non-shift mode is selected, don't return to default
            do_return = (selected_mode == modes[0] and not shift) or selected_mode == modes[1]
        else:
            do_return = selected_mode == modes[0]

        if do_return:
            self._selected_encoder_mode = None
            self._encoder_modes.selected_mode = self._view_encoder_mode()
        else:
            # Otherwise push mode chosen by shift button state
            self._selected_encoder_mode = modes[1 if shift and len(modes) > 1 else 0]
            self._encoder_modes.selected_mode = self._selected_encoder_mode

        self._update_led_feedback()

    def reset_selected_mode(self):
        # Back to the encoder of the current view, VOLUME / SWING / TEMPO off (VirtualDJ does the same with $encmode)
        self._selected_encoder_mode = None
        if self._encoder_modes != None:
            self._encoder_modes.selected_mode = self._view_encoder_mode()
        self._update_led_feedback()

    def _view_encoder_mode(self):
        # Encoder mode of the current view when no VOLUME / SWING / TEMPO mode is selected
        display_mode = self._display_modes.selected_mode if self._display_modes != None else None
        if display_mode in ("browser", "settings", "device"):
            return display_mode
        return "default"

    def set_encoder_modes(self, modes):
        self._encoder_modes = modes

    def set_display_modes(self, modes):
        self._display_modes = modes
        self._on_display_mode_changed.subject = modes
        if modes != None:
            self._on_display_mode_changed(modes)

    @listens("selected_mode")
    def _on_display_mode_changed(self, component):
        # Changing the view (mixer, device, browser, settings...) drops the VOLUME / SWING / TEMPO mode
        self.reset_selected_mode()

    def _update_led_feedback(self):
        mode = self._encoder_modes.selected_mode if self._encoder_modes != None else ""
        self.volume_button.is_on = mode in self.volume_modes
        self.swing_button.is_on = mode in self.swing_modes
        self.tempo_button.is_on = mode in self.tempo_modes

    def update(self):
        super().update()
        self._update_led_feedback()
