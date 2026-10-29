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

"""The screen bridge: what the script sends to the Pantallas program (display lines and a JSON state of the
view, knobs, session grid and browser, about 20 times per second over UDP), and the VirtualDJ tempo it gets
back for SHIFT + TEMPO. contrato/PROTOCOLO.md describes every message.

A mixin of MaschineMK3AsPush (moved from it as it was): it uses the script's other methods and state."""

from time import perf_counter
import json
import traceback
import socket
import time
import Live  # type: ignore
from Live.Base import Timer  # type: ignore
from ableton.v3.live import liveobj_name, liveobj_valid, parameter_owner, scene_index
from .DisplayDefinitions import TOUCH_STATES, get_display_value
from .Logger import logger
from . import Config
from . import Protocolo
from .MidiRouter import ENCODER_TEMPO_MODE, KNOB_COUNT, MIXER_DISPLAY_MODE
from .SessionNavigation import BROWSER_DISPLAY_MODE, SESSION_GRID_SCENES, SESSION_GRID_TRACKS

SCREENS_SUPERVISOR_ADDRESS = (Protocolo.HOST, Protocolo.SUPERVISOR_PORT)
VDJ_TEMPO_ADDRESS = (Protocolo.HOST, Protocolo.VDJ_TEMPO_PORT)
TEMPO_FLASH_SECONDS = 3.0  # how long SHIFT + TEMPO shows the tempo view when it wasn't the one on screen
VDJ_TEMPO_MAX_AGE = 3.0  # seconds: older than this, the driver isn't sending (closed) and the number can't be trusted
TEMPO_RANGE = (20.0, 999.0)  # Live's own limits
# Screen bridge: the Pantallas program drives the Maschine's screens (NI's software can't), so every display line
# the script sends also goes to it over UDP on localhost. The last lines are resent every second,
# so the bridge gets the text even when it starts after Live.
# About 30 times per second (a Live.Base.Timer: schedule_message ticks are ~100ms, too slow for smooth knobs)
# it also gets a JSON state (view, the 8 knob parameters, their tracks' meters, touched knob)
# so it can draw faders and knobs instead of text.
MCU_DISPLAY_HEADER = (0xF0, 0x00, 0x00, 0x66, 0x17, 0x12)
SCREEN_BRIDGE_ADDRESS = (Protocolo.HOST, Config.SCREEN_BRIDGE_PORT)
# Every JSON message carries the protocol version (Protocolo.VERSION), so the screens can tell when they and the
# script come from different installs. The mode messages (and the state) also say whether the pads are locked to
# VirtualDJ: this script owns the mode, and the screens pass it on to VirtualDJ's mapping so both stay in step
SCREEN_BRIDGE_MODE_VDJ = {
    pad_lock: json.dumps({"v": Protocolo.VERSION, "type": Protocolo.TYPE_MODE, "vdj": True,
                          "pad_lock": pad_lock}).encode("ascii")
    for pad_lock in (False, True)
}
SCREEN_BRIDGE_INTERVAL_MS = 50
SCREEN_BRIDGE_STALL_SECONDS = 0.5
SCREEN_BRIDGE_RESEND_TICKS = 20  # display lines are resent about once per second (at 20 FPS)
BROWSER_BRIDGE_ITEMS = 12  # items sent on each side of the selected one
TEMPO_SCREEN_RANGE = (60.0, 200.0)  # BPM range of the tempo bar on the screens
def _track_flag(track, name):
    # Live raises RuntimeError (not AttributeError) for mute / solo on the Main track, so getattr's default is not enough
    try:
        return bool(getattr(track, name))
    except Exception:
        return False


class ScreenBridgeMixin:
    _screen_bridge = None
    _screen_bridge_lines = None
    _screen_bridge_ticks = 0
    _screen_bridge_timer = None
    _screen_bridge_last_tick = 0.0
    _last_screen_bridge_payload = None
    _last_screen_bridge_dict = None
    _last_screen_bridge_time = 0.0
    _screen_bridge_timer_ok = False
    _screen_bridge_timer_repeats = False
    _screen_bridge_stall_logged = False
    _browser_bridge_key = None  # browser folder whose items are cached for the screens
    _browser_bridge_items = ()
    _browser_bridge_parent = None
    _screen_bridge_error_logged = False

    def _screen_bridge_session(self):
        # Clip grid for the session pad mode: SESSION_GRID_TRACKS tracks x SESSION_GRID_SCENES scenes from the
        # session ring's position (its first num_tracks columns are the ones on the pads)
        ring = getattr(self, "_session_ring", None)
        if ring is None:
            return None
        # The knobs follow the 8-track block when the ring moves
        session_volume = self.component_map["Session_Volume"]
        session_volume.block_start = self._session_block(ring)
        session_volume.refresh()
        tracks_to_use = getattr(ring, "tracks_to_use", None)
        tracks = list(tracks_to_use()) if callable(tracks_to_use) else self.song.visible_tracks
        scenes = self.song.scenes
        scenes_len = len(scenes)
        track_offset, scene_offset = ring.track_offset, ring.scene_offset
        # The screens show a block of SESSION_GRID_TRACKS tracks: moving the ring inside it only moves the
        # highlighted columns (the ones on the pads); leaving it moves the block SESSION_GRID_STEP tracks
        page_offset = self._session_block(ring)
        columns = self._grid_columns(tracks, page_offset, SESSION_GRID_TRACKS, scene_offset, SESSION_GRID_SCENES)
        return {
            "track_offset": track_offset,
            "page_offset": page_offset,
            "ring_column": track_offset - page_offset,
            "scene_offset": scene_offset,
            "ring_tracks": ring.num_tracks,
            # What the knobs control in the session view: "volume" (left arrow) or "fx" (right arrow)
            "knob_page": self.component_map["Session_Volume"].page,
            "scenes": [scenes[index].name if index < scenes_len else "" for index in
                       range(scene_offset, scene_offset + SESSION_GRID_SCENES)],
            "tracks": columns,
        }

    def _screen_bridge_grid_frame(self):
        ring = getattr(self, "_session_ring", None)
        if ring is None:
            return None
        block = self._session_block(ring)
        # "selected": which of the block's columns holds the selected track (the cursor), None if it's out of the block
        selected = None
        try:
            tracks = self._session_tracks_and_scenes()[1]
            selected_track = self.song.view.selected_track
            if selected_track in tracks:
                column = tracks.index(selected_track) - block
                if 0 <= column < SESSION_GRID_TRACKS:
                    selected = column
        except Exception:
            self._log_error_once("mixer cursor", traceback.format_exc())
        return {"ring_column": ring.track_offset - block, "ring_tracks": ring.num_tracks, "selected": selected}

    def _grid_columns(self, tracks, track_start, track_count, scene_start, scene_count):
        # Clip slots of a block of tracks x scenes, for the screens
        # The clip slot selected in Live (selected track x selected scene), marked on the screens
        highlighted = self.song.view.highlighted_clip_slot
        # The selected or locked track (the one the pads play), drawn in white on the screens
        target = self.component_map["Target_Track"].target_track
        columns = []
        num_tracks = len(tracks)
        for track_index in range(track_start, track_start + track_count):
            if track_index >= num_tracks:
                columns.append(None)
                continue
            track = tracks[track_index]
            slots = []
            clip_slots = track.clip_slots
            num_slots = len(clip_slots)
            for scene_index in range(scene_start, scene_start + scene_count):
                if scene_index >= num_slots:
                    slots.append(None)
                    continue
                slot = clip_slots[scene_index]
                if slot.has_clip:
                    clip = slot.clip
                    info = {"name": clip.name, "color": clip.color, "playing": clip.is_playing,
                            "triggered": clip.is_triggered, "recording": clip.is_recording}
                else:
                    info = {"empty": True, "stop": slot.has_stop_button, "triggered": slot.is_triggered}
                if liveobj_valid(highlighted) and slot == highlighted:
                    info["selected"] = True
                slots.append(info)
            columns.append({"name": track.name, "color": track.color, "slots": slots,
                            "target": liveobj_valid(target) and track == target,
                            "mute": _track_flag(track, "mute"),
                            "solo": _track_flag(track, "solo")})
        return columns

    def _screen_bridge_browser_grid(self):
        # Browser view: the session grid as it is (the pads' 4 tracks), to see where a loaded item will land.
        # If the selected slot leaves the pads, they move 4 tracks / 1 scene, like in the session view
        self._move_session_selection(0, 0)
        return self._screen_bridge_session()

    def _init_screen_bridge(self):
        self._vdj_tempo_socket = None
        self._vdj_tempo_last = None
        try:
            self._vdj_tempo_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._vdj_tempo_socket.bind(VDJ_TEMPO_ADDRESS)
            self._vdj_tempo_socket.setblocking(False)
        except OSError as error:
            logger.info(f"VirtualDJ tempo socket disabled: {error}")
            self._vdj_tempo_socket = None
        self._screen_bridge_lines = {}
        self._last_screen_bridge_payload = None
        self._last_screen_bridge_dict = None
        self._last_screen_bridge_time = 0.0
        if Config.SCREEN_BRIDGE_PORT is None:
            return
        try:
            self._screen_bridge = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._screen_bridge.setblocking(False)
        except OSError as error:
            # Runs before the control surface exists, so it can't use Live's log yet
            logger.info(f"Screen bridge disabled: {error}")
            self._screen_bridge = None

    def _copy_to_screen_bridge(self, midi_event_bytes):
        if self._screen_bridge is None or tuple(midi_event_bytes[:6]) != MCU_DISPLAY_HEADER:
            return
        message = bytes(midi_event_bytes)
        self._screen_bridge_lines[midi_event_bytes[6]] = message
        self._send_to_screen_bridge(message)

    def _encoder_tempo_mode(self):
        try:
            return self.component_map["Encoder_Modes"].selected_mode == ENCODER_TEMPO_MODE
        except (KeyError, AttributeError):
            return False

    def _turn_tempo(self, value):
        # Coarse turn: from the nearest whole BPM, so it always lands on round numbers. The step is the encoder's
        # (two's complement), so turning fast moves more than one BPM at a time
        step = value if value < 64 else value - 128
        if step == 0:
            return
        tempo = min(max(round(self.song.tempo) + step, TEMPO_RANGE[0]), TEMPO_RANGE[1])
        self.song.tempo = float(tempo)

    def _latest_vdj_tempo(self):
        # Reads everything the driver sent since the last click and keeps the newest: (bpm, deck) or None
        if self._vdj_tempo_socket is None:
            return None
        latest = None
        while True:
            try:
                data = self._vdj_tempo_socket.recv(512)
            except (BlockingIOError, OSError):
                break
            try:
                latest = json.loads(data.decode("ascii"))
            except ValueError:
                continue
        if latest is not None:
            self._vdj_tempo_last = latest
            if latest.get("v") != Protocolo.VERSION:
                # Still used (the fields may be the same), but the log says why it could go wrong
                sent = f"protocol v{latest['v']}" if latest.get("v") is not None else "an unversioned (old) protocol"
                self._log_error_once("protocol version", f"the screens driver sends {sent}, the script expects "
                                     f"v{Protocolo.VERSION}: install both from the same branch")
        message = self._vdj_tempo_last
        if not message or time.time() - message.get("t", 0) > VDJ_TEMPO_MAX_AGE:
            return None
        return message

    def _sync_tempo_with_virtualdj(self):
        message = self._latest_vdj_tempo()
        if message is None:
            text = "VirtualDJ: no data (is the screens driver running?)"
        elif not message.get("bpm"):
            text = "VirtualDJ: no track with a tempo"
        else:
            bpm = float(message["bpm"])
            if not TEMPO_RANGE[0] <= bpm <= TEMPO_RANGE[1]:
                text = f"VirtualDJ tempo out of range: {bpm:.2f}"
            else:
                self.song.tempo = bpm
                text = f"Tempo set to VirtualDJ deck {message.get('deck')}: {self.song.tempo:.2f} BPM"
                # The screens show the tempo view for a few seconds and go back to the view they were on (TEMPO alone
                # is what switches to it for good)
                self._send_to_screen_bridge(json.dumps({"v": Protocolo.VERSION, "type": Protocolo.TYPE_TEMPO_FLASH,
                                                        "bpm": self.song.tempo,
                                                        "seconds": TEMPO_FLASH_SECONDS}).encode("ascii"))
        self._log(f"SHIFT + click in TEMPO: {text}")
        self._c_instance.show_message(text)

    def _restart_screens(self):
        # The supervisor closes the screens in an orderly way and starts them again (it ignores a second request
        # within a few seconds). If it isn't running nothing answers, and the press is harmless
        try:
            self._screen_bridge.sendto(Protocolo.RESTART, SCREENS_SUPERVISOR_ADDRESS)
            self._log("SHIFT + MACRO: screens restart requested")
            self._c_instance.show_message("Restarting the screens...")
        except (OSError, AttributeError):
            self._log("SHIFT + MACRO: could not reach the screens' supervisor")

    def _send_to_screen_bridge(self, message):
        try:
            self._screen_bridge.sendto(message, SCREEN_BRIDGE_ADDRESS)
        except OSError:
            # Nobody listening or the send buffer is full: the next resend catches up
            pass

    def _screen_bridge_timer_tick(self):
        # Fast timer (~30 per second). The ~100ms watchdog below covers for it if it stops firing
        try:
            if not self._screen_bridge_timer_ok:
                self._screen_bridge_timer_ok = True
                self._c_instance.log_message(f"MaschineMK3AsPush: screen bridge timer running (repeat = {self._screen_bridge_timer_repeats})")
            self._screen_bridge_tick()
        finally:
            # A repeating timer re-arms itself; restart() from inside its own callback doesn't re-arm it in Live
            if self._screen_bridge_timer is not None and not self._screen_bridge_timer_repeats:
                self._screen_bridge_timer.restart()

    def _screen_bridge_watchdog(self):
        if self._screen_bridge is None:
            return
        try:
            if perf_counter() - self._screen_bridge_last_tick > SCREEN_BRIDGE_STALL_SECONDS:
                if not self._screen_bridge_stall_logged:
                    self._screen_bridge_stall_logged = True
                    self._c_instance.log_message("MaschineMK3AsPush: screen bridge timer not firing, using ~100ms ticks")
                self._screen_bridge_tick()
                if self._screen_bridge_timer is not None:
                    self._screen_bridge_timer.restart()
        finally:
            self.schedule_message(1, self._screen_bridge_watchdog)

    def _screen_bridge_tick(self):
        if self._screen_bridge is None:
            return
        self._log_state_changes()
        self._track_recorded_clips()
        self._screen_bridge_last_tick = perf_counter()
        # In VirtualDJ mode the display belongs to VirtualDJ: the bridge only learns the mode, so it can
        # pick it up when it starts while VirtualDJ mode is on
        if self._vdj_mode:
            self._send_to_screen_bridge(SCREEN_BRIDGE_MODE_VDJ[self._pad_lock])
            if self._encoder_tempo_mode():
                self._send_to_screen_bridge(json.dumps({"v": Protocolo.VERSION, "type": Protocolo.TYPE_TEMPO,
                                                        "bpm": self.song.tempo}).encode("ascii"))
        else:
            self._carry_selection_with_ring()
            self._send_screen_bridge_state()
            self._screen_bridge_ticks += 1
            if self._screen_bridge_ticks >= SCREEN_BRIDGE_RESEND_TICKS:
                self._screen_bridge_ticks = 0
                for message in self._screen_bridge_lines.values():
                    self._send_to_screen_bridge(message)

    def _start_screen_bridge(self):
        if self._screen_bridge is None:
            return
        try:
            try:
                self._screen_bridge_timer = Timer(callback = self._screen_bridge_timer_tick,
                                                  interval = SCREEN_BRIDGE_INTERVAL_MS, repeat = True, start = True)
                self._screen_bridge_timer_repeats = True
            except TypeError:
                # No repeat option: re-armed by restart() in the callback
                self._screen_bridge_timer = Timer(callback = self._screen_bridge_timer_tick,
                                                  interval = SCREEN_BRIDGE_INTERVAL_MS, start = True)
                self._screen_bridge_timer_repeats = False
        except Exception as error:
            self._c_instance.log_message(f"MaschineMK3AsPush: screen bridge timer failed ({error!r}), using ~100ms ticks")
            self._screen_bridge_timer = None
        # Always running: sends the state itself whenever the fast timer isn't firing
        self.schedule_message(1, self._screen_bridge_watchdog)

    def _send_screen_bridge_state(self):
        try:
            state = self._screen_bridge_state()
        except Exception as error:
            # Never let the bridge break the controller: log once and keep the text-only display
            self._log_error_once("screen bridge state", traceback.format_exc())
            return
        now = perf_counter()
        if self._last_screen_bridge_dict == state and now - self._last_screen_bridge_time < 0.5:
            return
        payload = json.dumps(state, separators=(",", ":")).encode("utf-8")
        self._last_screen_bridge_dict = state
        self._last_screen_bridge_payload = payload
        self._last_screen_bridge_time = now
        self._send_to_screen_bridge(payload)

    def _screen_bridge_state(self):
        if self._standby:
            return {"v": Protocolo.VERSION, "type": Protocolo.TYPE_STATE, "standby": True}
        knobs = []
        for index in range(KNOB_COUNT):
            parameter = self._get_knob_mapped_parameter(index)
            if not liveobj_valid(parameter):
                knobs.append(None)
                continue
            span = parameter.max - parameter.min
            knob = {
                "name": parameter.name,
                "value": (parameter.value - parameter.min) / span if span else 0.0,
                "text": get_display_value(parameter),
                "bipolar": parameter.min < 0 < parameter.max,
            }
            owner = parameter_owner(parameter)
            if not isinstance(owner, Live.Track.Track) and hasattr(owner, "canonical_parent") and isinstance(getattr(owner, "canonical_parent", None), Live.Track.Track):
                owner = owner.canonical_parent
            if isinstance(owner, Live.Track.Track):
                knob["track"] = owner.name
                knob["color"] = owner.color
                knob["mute"] = _track_flag(owner, "mute")
                knob["solo"] = _track_flag(owner, "solo")
                if owner.has_audio_output:
                    knob["meter"] = max(owner.output_meter_left, owner.output_meter_right)
            knobs.append(knob)

        view = self.component_map["Display_Modes"].selected_mode
        if view == MIXER_DISPLAY_MODE:
            mixer = self.component_map.get("Mixer")
            all_tracks = getattr(mixer, "_all_tracks", None)
            track_pos = getattr(mixer, "track_position", 0)
            if all_tracks is not None:
                for idx in range(min(len(knobs), KNOB_COUNT)):
                    if knobs[idx] is not None and "mute" not in knobs[idx]:
                        t_idx = track_pos + idx
                        if 0 <= t_idx < len(all_tracks):
                            trk = all_tracks[t_idx]
                            knobs[idx]["mute"] = _track_flag(trk, "mute")
                            knobs[idx]["solo"] = _track_flag(trk, "solo")

        device = getattr(self.component_map["Device"], "device", None)
        if callable(device):
            device = device()
        target_track = self.component_map["Target_Track"].target_track
        encoder_mode = self.component_map["Encoder_Modes"].selected_mode
        return {
            "encoder": self._screen_bridge_encoder(encoder_mode),
            "browser": self._screen_bridge_browser() if view == BROWSER_DISPLAY_MODE else None,
            "browser_grid": self._screen_bridge_browser_grid() if view == BROWSER_DISPLAY_MODE else None,
            "session_view": self._session_view,
            # The mixer shows the session grid's tracks: which of its 8 columns are on the pads
            "grid_frame": self._screen_bridge_grid_frame() if view == MIXER_DISPLAY_MODE else None,
            "session": self._screen_bridge_session() if self._session_view else None,
            "v": Protocolo.VERSION,
            "type": Protocolo.TYPE_STATE,
            "pad_lock": self._pad_lock,
            "view": view,
            "encoder_mode": encoder_mode,
            "mixer_parameter": getattr(self.component_map["Mixer"], "parameter_name", None),
            "device": liveobj_name(device) if liveobj_valid(device) else None,
            "device_color": self._device_color(device),
            "track": liveobj_name(target_track) if liveobj_valid(target_track) else None,
            "track_color": target_track.color if liveobj_valid(target_track) else None,
            "locked": self.component_map["Target_Track"].is_locked_to_track,
            "touched": TOUCH_STATES.active_index,
            # Every knob being touched right now (the screens give each one its own pop-up)
            "touched_all": self._touched_knobs(),
            # MUTE / SOLO / FOLLOW + knob act on the knob's track (stop, prelisten, launch): no value pop-up for them
            "no_popup": bool(self.elements.mute.is_pressed or self.elements.solo.is_pressed or self._follow_held),
            "knobs": knobs,
        }

    def _touched_knobs(self):
        # The touch buttons come from a matrix that can hand out None for a button that isn't there at that moment
        touched = []
        try:
            for index, button in enumerate(self.elements.knob_touch_buttons):
                if button is not None and button.is_pressed:
                    touched.append(index)
        except Exception:
            self._log_error_once("touched knobs", traceback.format_exc())
        return touched

    @staticmethod
    def _device_color(device):
        # Live has no color per device (as of 12.4): a device inside a rack takes its chain's color,
        # one on the track takes the track's
        if not liveobj_valid(device):
            return None
        color = getattr(device, "color", None)
        if color is not None:
            return color
        # canonical_parent: the rack chain (or drum pad chain) holding it, or the track itself
        parent = getattr(device, "canonical_parent", None)
        return getattr(parent, "color", None)

    def _screen_bridge_encoder(self, encoder_mode):
        # VOLUME = master volume, SWING = headphones (cue) volume: drawn like VirtualDJ's VOLUME / SWING.
        # TEMPO the same way: the bar spans TEMPO_SCREEN_RANGE, the text is the exact tempo
        master = self.song.master_track
        if encoder_mode == "tempo":
            low, high = TEMPO_SCREEN_RANGE
            tempo = self.song.tempo
            return {
                "mode": encoder_mode,
                "value": min(max((tempo - low) / (high - low), 0.0), 1.0),
                "text": f"{tempo:.2f} BPM",
                "meter": None,
            }
        if encoder_mode == "volume":
            parameter = master.mixer_device.volume
        elif encoder_mode == "swing":
            parameter = master.mixer_device.cue_volume
        else:
            return None
        span = parameter.max - parameter.min
        return {
            "mode": encoder_mode,
            "value": (parameter.value - parameter.min) / span if span else 0.0,
            "text": parameter.str_for_value(parameter.value),
            "meter": max(master.output_meter_left, master.output_meter_right) if encoder_mode == "volume" else None,
        }

    def _browser_level(self, folder):
        # Names of a browser folder's children, read once per folder: .children is slow on big folders
        items = []
        for item in folder.children:
            items.append({"name": item.name, "uri": getattr(item, "uri", None),
                          "folder": bool(item.is_folder or not item.is_loadable)})
        return items

    def _screen_bridge_browser(self):
        # The Browser component's own tree (encoder, push = load / enter, left / right = leave / enter folder)
        browser = self.component_map["Browser"]
        explorer = getattr(browser, "_explorer", None)
        if explorer is None:
            return None
        stack = explorer._tree_stack
        key = tuple(getattr(item, "uri", None) or item.name for item in stack)
        if key != self._browser_bridge_key:
            self._browser_bridge_key = key
            self._browser_bridge_items = self._browser_level(stack[-1])
            parent = None
            if len(stack) > 1:
                parent_items = self._browser_level(stack[-2])
                current = key[-1]
                index = next((i for i, item in enumerate(parent_items)
                              if (item["uri"] or item["name"]) == current), 0)
                parent = {"name": stack[-2].name, "items": parent_items, "selected": index}
            self._browser_bridge_parent = parent

        def window(items, selected):
            first = max(0, selected - BROWSER_BRIDGE_ITEMS)
            return {"first": first, "selected": selected, "count": len(items),
                    "items": [{"name": item["name"], "folder": item["folder"]}
                              for item in items[first:selected + BROWSER_BRIDGE_ITEMS + 1]]}

        parent = self._browser_bridge_parent
        return {
            "path": [item.name for item in stack[1:]],
            "folder": stack[-1].name,
            "list": window(self._browser_bridge_items, explorer.selected_item_index),
            "parent": dict(window(parent["items"], parent["selected"]), name=parent["name"]) if parent else None,
            "preview": browser.preview_enabled,
        }
