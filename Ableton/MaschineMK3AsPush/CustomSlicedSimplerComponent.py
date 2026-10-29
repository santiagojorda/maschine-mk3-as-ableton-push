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

import sys
from ableton.v3.base import listens, depends
from ableton.v3.live.util import liveobj_valid
from ableton.v3.control_surface.components import SlicedSimplerComponent
from ableton.v3.control_surface.components.sliced_simpler import DEFAULT_SIMPLER_TRANSLATION_CHANNEL
from ableton.v3.control_surface.controls import (
    ButtonControl,
    PlayableControl,
    control_list
)
from ableton.v3.control_surface.skin import LiveObjSkinEntry

from .Logger import logger
from .ClipNotesSelectMixin import ClipNotesSelectMixin

class CustomSlicedSimplerComponent(ClipNotesSelectMixin, SlicedSimplerComponent):
    _select_buttons = control_list(ButtonControl, control_count = 4, color = None)
    _has_slice_list = [False] * 4
    _show_message = None

    @depends(show_message = None)
    def __init__(self, show_message = None, *a, **k):
        super().__init__(*a, **k, matrix_always_listenable = True)
        self._show_message = show_message

    def set_select_buttons(self, matrix):
        self._select_buttons.set_control_element(matrix)
        self._update_slice_group()
        self._update_led_feedback()

    @_select_buttons.pressed
    def _on_select_buttons_pressed(self, target_button):
        for button in self._select_buttons:
            if button == target_button:
                self.position = button.index * 4
                logger.info(f"Slice group selected index = {button.index}")

    def _on_matrix_pressed(self, button):
        if hasattr(self, "delete_button") and self.delete_button.is_pressed:
            if not self._simpler_setup_is_valid():
                return
            slice_index = self._coordinate_to_slice_index(button.coordinate)
            if slice_index is not None:
                button.color = "SlicedSimpler.PadAction"
                clip = self.get_active_midi_clip()
                pitch = getattr(button, "identifier", None)
                if pitch is None and hasattr(self, "_note_translation_for_button"):
                    try:
                        pitch, _ = self._note_translation_for_button(button)
                    except Exception:
                        pitch = None
                notes_deleted = False
                if clip is not None and pitch is not None:
                    notes = clip.get_notes_extended(from_time=0.0, from_pitch=pitch, time_span=sys.maxsize, pitch_span=1)
                    if notes:
                        clip.remove_notes_extended(from_time=0.0, from_pitch=pitch, time_span=sys.maxsize, pitch_span=1)
                        notes_deleted = True
                        msg = f"Borradas {len(notes)} notas de slice {slice_index + 1} en clip '{clip.name or 'MIDI'}'"
                        if self._show_message:
                            self._show_message(msg)
                        logger.info(msg)
                        if hasattr(self, "notify") and hasattr(self, "notifications"):
                            try:
                                self.notify(self.notifications.Simpler.Slice.delete_notes, slice_index + 1)
                            except Exception:
                                pass
                if not notes_deleted:
                    self._delete_slice_at_index(slice_index)
                    msg = f"Slice {slice_index + 1} borrado"
                    if self._show_message:
                        self._show_message(msg)
                    logger.info(msg)
            return
        self.process_pad_pressed(button)
        return super()._on_matrix_pressed(button)

    def set_simpler_device(self, simpler_device):
        sample = self._simpler_device.sample if liveobj_valid(self._simpler_device) else None
        self._on_slices_changed.subject = sample
        super().set_simpler_device(simpler_device)

    def update(self):
        self._update_slice_group()
        super().update()

    def _update_led_feedback(self):
        super()._update_led_feedback()
        for button in self._select_buttons:
            if self._has_slice_list[button.index]:
                new_color = "SlicedSimpler.GroupHasSlice"
            else:
                new_color = "SlicedSimpler.Group"

            start_position = button.index * 4
            intersects = any([pos >= start_position and pos < start_position + 4 for pos in [self.position, self.position + 3]])
            if intersects:
                new_color += "Selected"

            button.color = LiveObjSkinEntry(new_color, self._target_track.target_track)

    def _update_button_color(self, button):
        super()._update_button_color(button)
        button.pressed_color = LiveObjSkinEntry("SlicedSimpler.SlicePressed", self._target_track.target_track)

    def _update_slice_group(self):
        slices = self._slices()
        logger.debug(f"Update slice group slices = {slices}, length = {len(slices)}")
        for index in range(self._select_buttons.control_count):
            self._has_slice_list[index] = len(slices) > index * 16

    @listens("slices")
    def _on_slices_changed(self):
        self._update_slice_group()
        self._update_led_feedback()
