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
from itertools import zip_longest
from ableton.v3.base import listens, listens_group, depends
from ableton.v3.live import liveobj_valid
from ableton.v3.control_surface.skin import LiveObjSkinEntry
from ableton.v3.control_surface.components import DrumGroupComponent
from ableton.v3.control_surface.controls import (
    control_matrix,
    PlayableControl,
    ButtonControl
)

from .Logger import logger
from .ClipNotesSelectMixin import ClipNotesSelectMixin

DEFAULT_GROUP_SIZE = 16

class CustomDrumGroupComponent(DrumGroupComponent, ClipNotesSelectMixin):
    select_buttons = control_matrix(ButtonControl, color = None)
    clear_all_solo_button = ButtonControl(color = None)
    clear_all_mute_button = ButtonControl(color = None)

    _group_start_notes = list(range(4, 128, DEFAULT_GROUP_SIZE))
    _has_chain_list = []
    _show_message = None

    @depends(show_message = None)
    def __init__(self, show_message = None, *a, **k):
        super().__init__(*a, **k, matrix_always_listenable = True)
        self._show_message = show_message

    def set_select_buttons(self, matrix):
        self.select_buttons.set_control_element(matrix)
        self._has_chain_list = [False] * self.select_buttons.control_count
        if matrix is not None:
            self._update_group_info()
            self._update_led_feedback()

    def set_drum_group_device(self, drum_group_device):
        super().set_drum_group_device(drum_group_device)
        self._on_chains_changed.replace_subjects(self._all_drum_pads)
        self._on_chains_changed(None)

    def set_matrix(self, matrix):
        super().set_matrix(matrix)
        # for button in self.matrix:
        #     button.set_mode(PlayableControl.Mode.playable_and_listenable)

    def _on_matrix_pressed(self, button):
        if self.delete_button.is_pressed:
            button.color = "DrumGroup.PadAction"
            pad = self._pad_for_button(button)
            pad_name = str(pad.name) if (pad is not None and hasattr(pad, "name")) else ""
            pitch = getattr(pad, "note", None)
            if pitch is None and hasattr(self, "_note_translation_for_button"):
                try:
                    pitch, _ = self._note_translation_for_button(button)
                except Exception:
                    pitch = None
            self._do_delete_pad(pad, pad_name, pitch = pitch)
            return
        self.process_pad_pressed(button)
        return super()._on_matrix_pressed(button)

    def _do_delete_pad(self, pad, pad_name, pitch = None):
        clip = self.get_active_midi_clip()
        if pitch is None and pad is not None:
            pitch = getattr(pad, "note", None)

        notes_deleted = False
        if clip is not None and pitch is not None:
            notes = clip.get_notes_extended(from_time = 0.0, from_pitch = pitch, time_span = sys.maxsize, pitch_span = 1)
            if notes:
                clip.remove_notes_extended(from_time = 0.0, from_pitch = pitch, time_span = sys.maxsize, pitch_span = 1)
                notes_deleted = True
                name_str = pad_name or (pad.name if (pad is not None and hasattr(pad, "name")) else f"Pitch {pitch}")
                msg = f"Borradas {len(notes)} notas de {name_str} en clip '{clip.name or 'MIDI'}'"
                if self._show_message:
                    self._show_message(msg)
                logger.info(msg)
                if hasattr(self, "notify") and hasattr(self, "notifications"):
                    try:
                        self.notify(self.notifications.DrumGroup.Pad.delete_notes, pad_name)
                    except Exception:
                        pass

        if not notes_deleted:
            chains = getattr(pad, "chains", []) if pad is not None else []
            if pad is not None and hasattr(pad, "delete_all_chains") and len(chains) > 0:
                pad.delete_all_chains()
                name_str = pad_name or getattr(pad, "name", f"Pitch {pitch}")
                msg = f"Pad borrado: {name_str}"
                if self._show_message:
                    self._show_message(msg)
                logger.info(msg)
                if hasattr(self, "notify") and hasattr(self, "notifications"):
                    try:
                        self.notify(self.notifications.DrumGroup.Pad.delete, pad_name)
                    except Exception:
                        pass
            elif not notes_deleted and clip is not None:
                name_str = pad_name or (pad.name if (pad is not None and hasattr(pad, "name")) else f"Pitch {pitch}")
                msg = f"No hay notas de {name_str} en clip '{clip.name or 'MIDI'}'"
                if self._show_message:
                    self._show_message(msg)
                logger.info(msg)
            elif not notes_deleted and clip is None and (pad is None or len(chains) == 0):
                msg = "No hay clip ni pad para borrar"
                if self._show_message:
                    self._show_message(msg)
                logger.info(msg)

    def _update_led_feedback(self):
        super()._update_led_feedback()
        for button, has_chain in zip(self.select_buttons, self._has_chain_list):
            row, column = button.coordinate

            # check visible pads window intersects each group regions
            # testing lower row (position) and upper row (position + 3) 
            start_position = int(self._group_start_notes[row * self.width + column] / 4)
            position = self._drum_group_scroller.position
            intersects = any([pos >= start_position and pos < start_position + 4 for pos in [position, position + 3]])

            if has_chain:
                new_color = "DrumGroup.GroupHasFilledPad"
            else:
                new_color = "DrumGroup.Group"

            if intersects:
                new_color += "Selected"

            button.color = LiveObjSkinEntry(new_color, self._target_track.target_track)

    def _update_button_color(self, button):
        super()._update_button_color(button)
        button.pressed_color = "DrumGroup.PadPressed"

    def _update_group_info(self):
        button_count = self.select_buttons.control_count
        groups = list(zip(range(button_count), self._group_start_notes))
        has_chain_list = [False] * button_count
        logger.info(f"Update group info groups = {groups}")

        for pad in self._all_drum_pads:
            if pad is not None:
                logger.debug(f"pad note {pad.note}, chain len = {len(pad.chains)}")
                for index, start_note in groups:
                    if pad.note < start_note + DEFAULT_GROUP_SIZE and len(pad.chains):
                        logger.debug(f"pad note {pad.note} group {index} has chain")
                        has_chain_list[index] = True
                        break
        
        logger.info(f"has_chain_list = {has_chain_list}")
        self._has_chain_list = has_chain_list

    @select_buttons.pressed
    def _on_group_select_buttons_pressed(self, target_button):
        for button in self.select_buttons:
            if button == target_button:
                logger.info(f"Drum group select index = {button.coordinate}")
                row, column = button.coordinate
                position = self._get_actual_group_scroll_position(row * self.width + column)
                logger.info(f"Scroll position = {position}")
                self._drum_group_scroller.position = position

    @clear_all_solo_button.pressed
    def _on_clear_all_solo_pressed(self, button):
        for pad in self._all_drum_pads:
            if pad.solo:
                pad.solo = False

    @clear_all_mute_button.pressed
    def _on_clear_all_mute_pressed(self, button):
        for pad in self._all_drum_pads:
            if pad.mute:
                pad.mute = False

    @listens_group("chains")
    def _on_chains_changed(self, subject):
        self._update_group_info()
        self._update_led_feedback()

    def _get_actual_group_scroll_position(self, group_index):
        # make sure not exceeding max scroll position when selecting last group
        start_note = min(self._group_start_notes[group_index], 128 - self.matrix.control_count)
        return int(start_note / 4)
