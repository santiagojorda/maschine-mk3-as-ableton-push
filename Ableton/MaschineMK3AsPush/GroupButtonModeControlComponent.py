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

class GroupButtonModeControlComponent(Component):
    notes_button = ButtonControl(color = "DefaultButton.Off", on_color = "DefaultButton.On")

    _pad_modes = None
    _group_button_modes = None

    def __init__(self, name = "Group_Button_Mode_Control", *a, **k):
        super().__init__(name, *a, **k)

    @notes_button.pressed
    def _on_notes_button_pressed(self, button):
        self.notes_button.is_on = not self.notes_button.is_on
        self._update_group_button_mode()

    def set_pad_modes(self, modes):
        self._pad_modes = modes
        self._on_pad_mode_changed.subject = modes
        if modes != None:
            self._update_group_button_mode()

    def set_group_button_modes(self, modes):
        self._group_button_modes = modes
        if modes != None:
            self._update_group_button_mode()

    def set_note_repeat_selector_state(self, enabled):
        self.notes_button.is_on = enabled
        self._update_group_button_mode()

    def get_note_repeat_selector_state(self):
        return self.notes_button.is_on

    def _update_group_button_mode(self):
        if self._group_button_modes == None or self._pad_modes == None:
            return

        if self.notes_button.is_on:
            self._group_button_modes.selected_mode = "note_repeat"
        else:
            try:
                self._group_button_modes.selected_mode = self._pad_modes.selected_mode
            except KeyError:
                # Pad modes without a group button counterpart (e.g. "vdj_locked") keep the current group buttons
                pass

    @listens("selected_mode")
    def _on_pad_mode_changed(self, component):
        self._update_group_button_mode()