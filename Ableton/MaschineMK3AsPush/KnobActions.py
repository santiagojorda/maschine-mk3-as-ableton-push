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

"""What a modifier + touching a knob does to the knob's parameter or track (RESTART, ERASE, MUTE, SOLO, FOLLOW;
MidiRouter decides which one), and SHIFT + RESTART / RESTART + SOLO for every track.

A mixin of MaschineMK3AsPush (moved from it as it was): it uses the script's other methods and state."""

import Live  # type: ignore
from ableton.v3.live import liveobj_valid, parameter_owner


class KnobActionsMixin:

    def _reset_all_volumes(self):
        # Every track and return back to its volume's default (0 dB); the master volume is left alone
        count = 0
        for track in list(self.song.tracks) + list(self.song.return_tracks):
            volume = track.mixer_device.volume
            volume.value = volume.default_value
            count += 1
        self._c_instance.show_message(f"Volumes reset to default ({count} tracks)")
        self._c_instance.log_message(f"MaschineMK3AsPush: {count} volumes reset to default")

    def _set_knob_parameter(self, index, default):
        parameter = self._get_knob_mapped_parameter(index)
        if not liveobj_valid(parameter):
            return
        if default:
            value = getattr(parameter, "default_value", parameter.min)
        else:
            value = 0.0 if parameter.min < 0 < parameter.max else parameter.min
        parameter.value = min(max(value, parameter.min), parameter.max)

    def _knob_track(self, index, what):
        # In the session view knob N is the track of column N of the grid on the screens, whatever the knobs control
        # (volume or, in the FX page, the selected device): MUTE / SOLO / FOLLOW + knob work the same in both pages
        if self._session_view:
            ring, tracks, _ = self._session_tracks_and_scenes()
            position = self._session_block(ring) + index
            if 0 <= position < len(tracks) and liveobj_valid(tracks[position]):
                return tracks[position]
            self._log(f"{what} + knob {index + 1}: no track in that column of the grid")
            self._c_instance.show_message("No track in that column")
            return None
        # Elsewhere the track of a knob is the owner of the parameter it controls (volume, pan or send of a track)
        parameter = self._get_knob_mapped_parameter(index)
        owner = parameter_owner(parameter) if liveobj_valid(parameter) else None
        if not isinstance(owner, Live.Track.Track):
            self._log(f"{what} + knob {index + 1}: that knob doesn't control a track")
            self._c_instance.show_message("That knob doesn't control a track")
            return None
        return owner

    def _clear_prelisten(self):
        count = 0
        for track in list(self.song.tracks) + list(self.song.return_tracks):
            if track.solo:
                track.solo = False
                count += 1
        self._log(f"RESTART + SOLO: {count} tracks out of the prelisten")

    def _toggle_knob_track_prelisten(self, index):
        track = self._knob_track(index, "SOLO")
        if track is None:
            return
        track.solo = not track.solo
        self._log(f"SOLO + knob {index + 1}: '{track.name}' prelisten = {track.solo}")

    def _launch_knob_track_clip(self, index):
        track = self._knob_track(index, "FOLLOW")
        scene = self.song.view.selected_scene
        scenes = list(self.song.scenes)
        if track is None or scene not in scenes:
            return
        slots = getattr(track, "clip_slots", ())
        position = scenes.index(scene)
        if position >= len(slots) or not slots[position].has_clip:
            self._log(f"FOLLOW + knob {index + 1}: no clip on '{track.name}' in scene {position + 1}")
            return
        slots[position].fire()
        self._log(f"FOLLOW + knob {index + 1}: launched '{slots[position].clip.name}' on '{track.name}' (scene {position + 1})")

    def _stop_knob_track_clip(self, index):
        owner = self._knob_track(index, "MUTE")
        if owner is None:
            return
        try:
            has_clips = len(owner.clip_slots) > 0
        except Exception:
            has_clips = False
        if not has_clips:
            self._c_instance.show_message(f"{owner.name} has no clips")
            return
        playing = owner.playing_slot_index >= 0
        owner.stop_all_clips()
        self._log(f"MUTE + knob {index + 1}: stopped the clips of '{owner.name}' (was playing = {playing})")
        self._c_instance.show_message(f"Stopped {owner.name}")
