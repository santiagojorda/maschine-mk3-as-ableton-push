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
from ableton.v3.control_surface.controls import (
    ButtonControl,
    control_matrix
)
from ableton.v3.base import depends
from ableton.v3.live import liveobj_valid

from .Logger import logger

class ClipNotesSelectMixin():
    select_note_button = ButtonControl(color = None)
    erase_note_button = ButtonControl(color = None)

    _sequencer_clip = None
    _trigger_deselect = True

    @depends(sequencer_clip = None)
    def __init__(self, sequencer_clip = None, *a, **k):
        super().__init__(*a, **k)
        self._sequencer_clip = sequencer_clip

    def get_active_midi_clip(self):
        song = getattr(self, "song", None)
        if song is not None:
            view = getattr(song, "view", None)
            if view is not None:
                detail = getattr(view, "detail_clip", None)
                if liveobj_valid(detail) and getattr(detail, "is_midi_clip", False):
                    return detail
                slot = getattr(view, "highlighted_clip_slot", None)
                if liveobj_valid(slot) and getattr(slot, "has_clip", False) and liveobj_valid(getattr(slot, "clip", None)):
                    if getattr(slot.clip, "is_midi_clip", False):
                        return slot.clip
        target_track = getattr(self, "_target_track", None)
        if target_track is not None:
            clip = getattr(target_track, "target_clip", None)
            if liveobj_valid(clip) and getattr(clip, "is_midi_clip", False):
                return clip
        seq_clip = getattr(self, "_sequencer_clip", None)
        if seq_clip is not None:
            clip = getattr(seq_clip, "clip", None)
            if liveobj_valid(clip) and getattr(clip, "is_midi_clip", False):
                return clip
        return None

    def select_notes(self, pitch):
        clip = self._sequencer_clip.clip
        if clip != None:
            notes = clip.get_notes_extended(
                from_time = 0,
                from_pitch = pitch,
                time_span = clip.length,
                pitch_span = 1)
            
            note_ids = [note.note_id for note in notes]
            if self._trigger_deselect:
                clip.deselect_all_notes()
                self._trigger_deselect = False
            clip.select_notes_by_id(note_ids)

    @select_note_button.value
    def _on_note_select_button_changed(self, value, button):
        self._set_control_pads_from_script(button.is_pressed)
        if not button.is_pressed:
            self._trigger_deselect = True

    @select_note_button.double_clicked
    def _on_note_select_double_clicked(self, button):
        clip = self._sequencer_clip.clip
        if clip != None:
            clip.deselect_all_notes()

    @erase_note_button.pressed
    def _on_note_erase_button_pressed(self, button):
        clip = self._sequencer_clip.clip
        if clip != None:
            selected_notes = clip.get_selected_notes_extended()
            clip.remove_notes_by_id([note.note_id for note in selected_notes])

    def _set_control_pads_from_script(self, takeover_pads):
        super()._set_control_pads_from_script(takeover_pads or self.select_note_button.is_pressed)

    def process_pad_pressed(self, button):
        if self.select_note_button.is_pressed:
            pitch, _ = self._note_translation_for_button(button)
            self.select_notes(pitch)
    