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

"""The session view of the Maschine (ARRANGER): the cursor and the grid on the screens, moving the pads' grid,
and the scene and clip actions (SCENE + click, PATTERN, EVENTS, VARIATION).

A mixin of MaschineMK3AsPush (moved from it as it was): it uses the script's other methods and state."""

from time import perf_counter
import traceback
from ableton.v3.live import liveobj_valid, scene_index
from .MidiRouter import MIXER_DISPLAY_MODE, SESSION_DISPLAY_MODE, SESSION_NAV_PUSH, SESSION_NAV_TILTS, SESSION_NAV_TURN, SESSION_VIEW_BUTTON

SESSION_GRID_TRACKS = 8
SESSION_GRID_SCENES = 4
RECORDED_CHECK_SECONDS = 0.1  # how often the tracks are looked at for a recording that started or ended
SESSION_GRID_STEP = 4  # the grid on the screens moves sideways in steps of 4 tracks
BROWSER_DISPLAY_MODE = "browser"


class SessionNavigationMixin:
    _session_block_start = 0  # first track of the session grid on the screens
    _recorded_checked = 0.0
    _recording_slots = ()  # clip slots recording right now
    _last_recorded = None  # clip slot of the last recording that ended
    _ring_offsets_seen = None  # (track, scene) offsets of the session ring at the last tick

    def _handle_session_navigation(self, midi_bytes):
        key, value = midi_bytes[:2], midi_bytes[2]
        # In the mixer the same moves walk the tracks (the cursor shown on the screens, blocks of 4 like in the
        # session view); there is no clip grid there, so no scene moves and no clip to fire
        in_session = self._session_view
        if key == SESSION_NAV_PUSH:
            if value > 0 and in_session:
                slot = self.song.view.highlighted_clip_slot
                if liveobj_valid(slot):
                    slot.fire()
            return
        if key == SESSION_NAV_TURN:
            step = value if value < 64 else value - 128  # two's complement
            if step == 0:
                return
            delta = (1 if step > 0 else -1, 0)  # turning moves sideways, between tracks
        else:
            if value == 0:  # tilt released
                return
            delta = SESSION_NAV_TILTS[key]
        if not in_session:
            delta = (delta[0], 0)
            if delta[0] == 0:
                return
        with self.component_guard():
            if self.elements.shift.is_pressed:
                self._move_session_ring(delta[0] * SESSION_GRID_STEP, delta[1])  # 4 tracks sideways, 1 scene
            else:
                self._move_session_selection(*delta)

    def _session_tracks_and_scenes(self):
        ring = self._session_ring
        tracks_to_use = getattr(ring, "tracks_to_use", None)
        tracks = list(tracks_to_use()) if callable(tracks_to_use) else list(self.song.visible_tracks)
        return ring, tracks, list(self.song.scenes)

    def _session_block(self, ring):
        # First track of the SESSION_GRID_TRACKS-track block shown on the screens. It moves in steps of
        # SESSION_GRID_STEP, only when the pads (the session ring) or the selected slot leave it
        start = self._session_block_start
        first, last = ring.track_offset, ring.track_offset + ring.num_tracks
        while first < start:
            start -= SESSION_GRID_STEP
        while last > start + SESSION_GRID_TRACKS:
            start += SESSION_GRID_STEP
        self._session_block_start = max(0, start)
        return self._session_block_start

    def _move_session_selection(self, track_delta, scene_delta, follow = True):
        # Moves Live's selected clip slot. Leaving the pads moves them SESSION_GRID_STEP tracks sideways (and
        # the grid on the screens, when the pads leave it) or one scene up / down. follow = False keeps the
        # selection inside the grid instead (after SHIFT moved the grid itself)
        ring, tracks, scenes = self._session_tracks_and_scenes()
        if not tracks or not scenes:
            return
        view = self.song.view
        start = self._session_block(ring)
        scene_offset = ring.scene_offset
        track_index = tracks.index(view.selected_track) if view.selected_track in tracks else start
        scene_index = scenes.index(view.selected_scene) if view.selected_scene in scenes else scene_offset
        track_index = min(max(track_index + track_delta, 0), len(tracks) - 1)
        scene_index = min(max(scene_index + scene_delta, 0), len(scenes) - 1)
        if follow:
            # The pads (the session ring) follow the selected slot, SESSION_GRID_STEP tracks at a time
            # (e.g. moving onto the right screen moves them there); the block on the screens follows the pads
            track_offset = ring.track_offset
            while track_index < track_offset:
                track_offset -= SESSION_GRID_STEP
            while track_index >= track_offset + ring.num_tracks:
                track_offset += SESSION_GRID_STEP
            track_offset = min(max(track_offset, 0), max(len(tracks) - 1, 0))
            if scene_index < scene_offset:
                scene_offset = scene_index
            elif scene_index >= scene_offset + SESSION_GRID_SCENES:
                scene_offset = scene_index - SESSION_GRID_SCENES + 1
            if track_offset != ring.track_offset or scene_offset != ring.scene_offset:
                ring.set_offsets(track_offset, scene_offset)
                self._ring_offsets_seen = (ring.track_offset, ring.scene_offset)
                self._session_block(ring)
        else:
            track_index = min(max(track_index, start), min(start + SESSION_GRID_TRACKS, len(tracks)) - 1)
            scene_index = min(max(scene_index, scene_offset),
                              min(scene_offset + SESSION_GRID_SCENES, len(scenes)) - 1)
        if view.selected_track != tracks[track_index]:
            view.selected_track = tracks[track_index]
        if view.selected_scene != scenes[scene_index]:
            view.selected_scene = scenes[scene_index]

    def _move_session_ring(self, track_delta, scene_delta):
        ring, tracks, scenes = self._session_tracks_and_scenes()
        track_offset = min(max(ring.track_offset + track_delta, 0), max(len(tracks) - 1, 0))
        scene_offset = min(max(ring.scene_offset + scene_delta, 0), max(len(scenes) - 1, 0))
        ring.set_offsets(track_offset, scene_offset)
        self._ring_offsets_seen = (ring.track_offset, ring.scene_offset)
        # The selected clip slot stays visible
        self._move_session_selection(0, 0, follow = False)

    def _track_recorded_clips(self):
        # Live doesn't keep "the last clip recorded", so it is noted here: a track whose playing slot is recording is
        # remembered, and when the recording ends that slot becomes the last recorded clip. Called from the screen
        # bridge tick, about every RECORDED_CHECK_SECONDS
        now = perf_counter()
        if now - self._recorded_checked < RECORDED_CHECK_SECONDS:
            return
        self._recorded_checked = now
        recording = []
        try:
            for track in self.song.tracks:
                index = track.playing_slot_index  # also covers the slot that is recording
                if 0 <= index < len(track.clip_slots):
                    slot = track.clip_slots[index]
                    if slot.has_clip and slot.clip.is_recording:
                        recording.append(slot)
        except Exception:
            self._log_error_once("recorded clips", traceback.format_exc())
            return
        for slot in self._recording_slots:
            if slot not in recording and liveobj_valid(slot) and slot.has_clip:
                self._last_recorded = slot
                self._log(f"clip recorded: '{slot.clip.name}' on '{slot.canonical_parent.name}'")
        self._recording_slots = recording

    def _delete_clip(self):
        # VARIATION: in the session view, the clip under the cursor; in the other views, the last clip recorded (the
        # one being recorded now, if there is one)
        if self._session_view:
            slot = self.song.view.highlighted_clip_slot
            missing = "No clip under the cursor"
        else:
            slot = self._recording_slots[-1] if self._recording_slots else self._last_recorded
            missing = "No recorded clip to delete"
        if not liveobj_valid(slot) or not slot.has_clip:
            self._log(f"VARIATION: {missing}")
            self._c_instance.show_message(missing)
            return
        name, track_name = slot.clip.name, slot.canonical_parent.name
        slot.delete_clip()
        if slot == self._last_recorded:
            self._last_recorded = None
        self._c_instance.show_message(f"Clip deleted: {name} ({track_name}) - Ctrl+Z to undo")
        self._log(f"deleted clip '{name}' on '{track_name}' ({'under the cursor' if self._session_view else 'last recorded'})")

    @property
    def _session_view(self):
        return self.component_map["Display_Modes"].selected_mode == SESSION_DISPLAY_MODE

    def _show_session_view(self):
        with self.component_guard():
            self.component_map["Display_Modes"].selected_mode = SESSION_DISPLAY_MODE
        self.application.view.show_view("Session")
        self._update_session_view_led()

    def _update_session_view_led(self):
        # Through _do_send_midi: in VirtualDJ mode the LEDs belong to VirtualDJ
        self._do_send_midi((SESSION_VIEW_BUTTON[0], SESSION_VIEW_BUTTON[1], 127 if self._session_view else 0))

    def _carry_selection_with_ring(self):
        # In the browser and session views the grid on the screens is the pads' grid: when something else moves the
        # session ring (A-H in the session pad mode jump between grids), the selected clip slot goes along, to the
        # same place of the new grid, instead of the grid snapping back to the selection
        ring = getattr(self, "_session_ring", None)
        if ring is None or self._standby:
            return
        self.component_map["Session_Zones"].refresh()
        if self.component_map["Display_Modes"].selected_mode == MIXER_DISPLAY_MODE:
            self._mixer_follow_ring(ring)
        offsets = (ring.track_offset, ring.scene_offset)
        last, self._ring_offsets_seen = self._ring_offsets_seen, offsets
        if last is None or offsets == last:
            return
        self._log(f"session ring moved: tracks {last[0]} -> {offsets[0]}, scenes {last[1]} -> {offsets[1]}")
        self._mixer_follow_ring(ring)
        if self.component_map["Display_Modes"].selected_mode not in (BROWSER_DISPLAY_MODE, SESSION_DISPLAY_MODE, MIXER_DISPLAY_MODE):
            return
        _, tracks, scenes = self._session_tracks_and_scenes()
        view = self.song.view
        if not tracks or not scenes or view.selected_track not in tracks or view.selected_scene not in scenes:
            return
        track_index = min(max(tracks.index(view.selected_track) + offsets[0] - last[0], 0), len(tracks) - 1)
        scene_index = min(max(scenes.index(view.selected_scene) + offsets[1] - last[1], 0), len(scenes) - 1)
        view.selected_track = tracks[track_index]
        view.selected_scene = scenes[scene_index]

    def _scroll_grid(self, direction):
        # Moves the pads' grid SESSION_GRID_STEP tracks to the left (-1) or right (1). The next screen bridge tick sees
        # the ring move and takes the selected slot and the mixer along (_carry_selection_with_ring)
        ring, tracks, _ = self._session_tracks_and_scenes()
        new_offset = min(max(ring.track_offset + direction * SESSION_GRID_STEP, 0), max(len(tracks) - 1, 0))
        if new_offset == ring.track_offset:
            self._log(f"grid already at the {'end' if direction > 0 else 'start'} of the tracks")  # nothing shown
            return
        ring.set_offsets(new_offset, ring.scene_offset)

    def _mixer_follow_ring(self, ring):
        # The 8-track mixer shows the same 8 tracks as the session grid on the screens (its own scrolling by one track
        # is not used): moving the pads' grid (A-H in the session pad mode, left / right) moves the mixer too
        mixer = self.component_map.get("Mixer")
        if mixer is None or not hasattr(mixer, "track_position"):
            return
        start = self._session_block(ring)
        if mixer.track_position != start:
            with self.component_guard():
                mixer.track_position = start
            self._log(f"mixer follows the pads' grid: tracks {start + 1}-{start + 8}")

    def _launch_cursor_scene(self):
        scene = self.song.view.selected_scene
        if not liveobj_valid(scene):
            return
        scene.fire()
        name = scene.name or f"{list(self.song.scenes).index(scene) + 1}"
        self._log(f"SCENE + click: scene '{name}' launched")
        self._c_instance.show_message(f"Scene launched: {name}")

    def _capture_scene(self):
        # What Push does: a new scene under the selected one with the clips that are playing now (and it launches, so
        # they keep playing in sync)
        self.song.capture_and_insert_scene()
        self._log("PATTERN: playing clips captured into a new scene")
        self._c_instance.show_message("Scene captured from the playing clips")

    def _new_scene_below_cursor(self):
        # A new empty scene under the selected one: the clip of the cursor's track stops (the other tracks keep
        # playing) and the cursor goes to the new scene, so the next clip of that track is recorded or put there
        view = self.song.view
        scenes = list(self.song.scenes)
        position = scenes.index(view.selected_scene) + 1 if view.selected_scene in scenes else len(scenes)
        track = view.selected_track
        if liveobj_valid(track) and len(getattr(track, "clip_slots", ())) > 0:
            track.stop_all_clips()
        view.selected_scene = self.song.create_scene(position)
        self._log(f"EVENTS: new scene {position + 1}, the cursor's track stopped, the cursor is there")
