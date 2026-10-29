# ==================================================
#
# This file is part of CustomMaschineMK3.
# CustomMaschineMK3 is free software licensed under GPL-3.0.
# For more details, see "LICENSE" file.
# 
# Copyright (C) 2024-2025 chiaki
#
# ==================================================

from functools import partial
from itertools import product
from time import perf_counter, sleep
import json
import traceback
import socket
import time

import Live # type: ignore
from Live.Base import Timer # type: ignore

from ableton.v3.base import lazy_attribute, const, listens
from ableton.v3.live import liveobj_name, liveobj_valid, parameter_owner, scene_index
from ableton.v3.control_surface import (
    ControlSurface,
    ControlSurfaceSpecification,
    IdentificationComponent
)

from ableton.v3.control_surface.component import (
    Component
)

from ableton.v3.control_surface.display import DisplaySpecification

from ableton.v3.control_surface.components import (
    SessionRingComponent,
    PlayableComponent,
    NoteEditorComponent,
    NoteEditorPaginator,
    StepSequenceComponent,
    SequencerClip,
    GridResolutionComponent,
    SessionComponent,
    TargetTrackComponent,
    DEFAULT_SIMPLER_TRANSLATION_CHANNEL,
    DEFAULT_DRUM_TRANSLATION_CHANNEL
)

from ableton.v3.control_surface.components.grid_resolution import GridResolution
from Live.Clip import GridQuantization # type: ignore

from ableton.v3.control_surface.elements import SimpleColor, RgbColor, create_rgb_color

from .ControlElements import ControlElements
from .Mappings import create_mappings
from .ColorSkin import MaschineSkin
from .DisplayDefinitions import (
    MaschineDisplay,
    TOUCH_STATES,
    get_display_value,
    make_mcu_display_header,
    make_display_sysex_message
)
from .GroovePoolComponent import GroovePoolComponent
from .MasterVolumeComponent import MasterVolumeComponent, CueVolumeComponent
from .MaschinePlayableComponent import MaschinePlayableComponent, DEFAULT_NOTE_TRANSLATION_CHANNEL
from .CustomDrumGroupComponent import CustomDrumGroupComponent
from .MiscControlComponent import MiscControlComponent
from .CustomDeviceComponent import (
    CUSTOM_BANK_DEFINITIONS,
    CustomDeviceDecoratorFactory,
    CustomDeviceComponent
)
from .CustomDeviceNavigationComponent import CustomDeviceNavigationComponent
from .SessionVolumeComponent import SessionVolumeComponent
from .SessionZonesComponent import SessionZonesComponent
from .CustomMixerComponent import CustomMixerComponent
from .MaschineMixerComponent import MaschineMixerComponent
from .CustomClipActionsComponent import CustomClipActionsComponent
from .CustomSlicedSimplerComponent import CustomSlicedSimplerComponent
from .NoteRepeatComponent import NoteRepeatComponent
from .VelocityLevelsComponent import VelocityLevelsComponent
from .ScaleSystemComponent import ScaleSystemComponent
from .SelectedParameterControlComponent import SelectedParameterControlComponent
from .CustomNoteEditorComponent import CustomNoteEditorComponent, CustomStepSequenceComponent
from .CustomLoopSelectorComponent import CustomLoopSelectorComponent
from .ClipEditorComponent import ClipEditorComponent
from .BrowserComponent import BrowserComponent
from .RecordingMethod import FixedLengthRecordingMethod, CustomViewBasedRecordingComponent
from .EncoderModeControlComponent import EncoderModeControlComponent
from .GroupButtonModeControlComponent import GroupButtonModeControlComponent
from .CustomTransportComponent import CustomTransportComponent
from .SettingsComponent import SettingsRepository, SettingsComponent
from .CustomClipSlotComponent import LEDBlinker, CustomClipSlotComponent
from .PageableBackgroundComponent import PageableBackgroundComponent

from .Logger import logger
from . import Config
from . import Protocolo

# VirtualDJ mode: "SAMPLING" hands the Maschine over to VirtualDJ, "PLUGIN" or "MIXER" brings it back.
# (status byte, CC number) of each button, all of them on MIDI channel 2
VDJ_ENTER_BUTTON = (0xB1, 39)
# Standby: SHIFT + CHANNEL puts the Maschine to rest (everything off, welcome on the screens); CHANNEL wakes it,
# and so do the mode buttons (SAMPLING also enters VirtualDJ mode, MIXER and PLUGIN select their view)
BUTTON_NAMES = {
    8: "EncoderPush", 30: "EncoderUp", 31: "EncoderRight", 32: "EncoderDown", 33: "EncoderLeft", 34: "Channel",
    35: "Plugin", 36: "Arranger", 37: "Mixer", 38: "Browser", 39: "Sampling", 40: "File", 41: "Setting", 42: "Auto",
    43: "Macro", 44: "Volume", 45: "Swing", 46: "NoteRep", 47: "Tempo", 48: "Lock", 49: "Pitch", 50: "Mod",
    51: "Perform", 52: "Notes", 53: "Restart", 54: "Erase", 55: "Tap", 56: "Follow", 57: "Play", 58: "Rec",
    59: "Stop", 80: "FixedVel", 81: "PadMode", 82: "Keyboard", 83: "Chords", 84: "Step", 85: "Scene",
    86: "Pattern", 87: "Events", 88: "Variation", 89: "Duplicate", 90: "Select", 91: "Solo", 92: "Mute",
    100: "GroupA", 101: "GroupB", 102: "GroupC", 103: "GroupD", 104: "GroupE", 105: "GroupF", 106: "GroupG",
    107: "GroupH", 110: "Left", 111: "Right",
}
LEFT_BUTTON = (0xB1, 110)
RIGHT_BUTTON = (0xB1, 111)
STANDBY_BUTTON = (0xB1, 34)
SHIFT_BUTTON = (0xB1, 119)
# SHIFT + MACRO asks the screens' supervisor (the driver) to restart the screens, in case they freeze or draw garbage
MACRO_BUTTON = (0xB1, 43)
SCREENS_SUPERVISOR_ADDRESS = (Protocolo.HOST, Protocolo.SUPERVISOR_PORT)
# TEMPO mode of the encoder: turning moves the tempo in whole BPM (90.09 -> 91.00 up, 89.00 down; with SHIFT it stays
# fine), and SHIFT + TEMPO, in any view, sets it to the tempo of the VirtualDJ deck the driver picks as reference
# without changing the view. The driver (vdj_master.py) sends it here by UDP twice a second
ENCODER_TEMPO_MODE = "tempo"
ENCODER_TURN_BUTTON = (0xB1, 7)
TEMPO_BUTTON = (0xB1, 47)
# SCENE + click of the encoder launches the scene under the cursor (all its clips). PATTERN captures the clips that are
# playing into a new scene, like Push's "capture and insert scene" (it used to be the fixed length recording button)
SCENE_BUTTON = (0xB1, 85)
PATTERN_BUTTON = (0xB1, 86)
VDJ_TEMPO_ADDRESS = (Protocolo.HOST, Protocolo.VDJ_TEMPO_PORT)
TEMPO_FLASH_SECONDS = 3.0  # how long SHIFT + TEMPO shows the tempo view when it wasn't the one on screen
VDJ_TEMPO_MAX_AGE = 3.0  # seconds: older than this, the driver isn't sending (closed) and the number can't be trusted
TEMPO_RANGE = (20.0, 999.0)  # Live's own limits
STANDBY_WAKE_BUTTONS = ((0xB1, 34), (0xB1, 35), (0xB1, 36), (0xB1, 37))
# Only the controllers that are LEDs: sending a value to all 128 also hits MIDI's special messages
# (CC 120-127 channel mode, RPN / NRPN, bank select...) and can leave the Maschine in an odd state
STANDBY_LED_CCS = (34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 47, 48, 49, 52, 53, 55, 56, 57, 58, 59, 80, 81, 82, 83, 84, 87, 88, 100, 101, 102, 103, 104, 105, 106, 107, 110, 111)
STANDBY_LED_NOTES = range(4)  # buttons 1-4 above the screens (channel 2)
VDJ_EXIT_BUTTONS = ((0xB1, 35), (0xB1, 36), (0xB1, 37))
# Buttons that keep controlling Ableton even in VirtualDJ mode: PLAY, STOP, TAP (messages and their LEDs).
# SHIFT (sysex from the MK3 / Plus) also gets through, so SHIFT + STOP and SHIFT + TAP (metronome) work too.
ABLETON_ALWAYS_BUTTONS = ((0xB1, 57), (0xB1, 59), (0xB1, 55))
SHIFT_SYSEX_PREFIX = (0xF0, 0x00, 0x21, 0x09)
# VOLUME / SWING / TEMPO (encoder = master / cue volume / tempo) are shared with VirtualDJ: in VirtualDJ mode Ableton still follows
# their presses (without LEDs) so the encoder mode stays the same in both programs
SHARED_ENCODER_MODE_BUTTONS = ((0xB1, 44), (0xB1, 45), (0xB1, 47))  # VOLUME, SWING, TEMPO (mutually exclusive)
# "FOLLOW" toggles Ableton's Link in Ableton (replaces its record quantize function).
# In VirtualDJ mode it belongs to VirtualDJ (its Ableton Link effect) and its LED too.
LINK_BUTTON = (0xB1, 56)
PAD_LOCK_MODE = "vdj_locked"
# Ticks (about 100ms each) to wait before the full LEDs and display refresh after leaving VirtualDJ mode,
# so VirtualDJ's last messages don't overwrite Ableton's state. The display itself is redrawn immediately too.
VDJ_REFRESH_DELAY = 1
# "LOCK" pressed in VirtualDJ mode keeps the pads with VirtualDJ after going back to Ableton ("pad lock").
# Pressing "LOCK" in Ableton releases them. VirtualDJ's mapping mirrors the same logic.
PAD_LOCK_BUTTON = (0xB1, 48)
# Locked to VirtualDJ along with the pads: the A-H group buttons and the touch strip (VirtualDJ's crossfader)
GROUP_BUTTON_CCS = range(100, 108)
PAD_NOTES = range(60, 76)
# Screen bridge: the Pantallas program drives the Maschine's screens (NI's software can't), so every display line
# the script sends also goes to it over UDP on localhost. The last lines are resent every second,
# so the bridge gets the text even when it starts after Live.
# About 30 times per second (a Live.Base.Timer: schedule_message ticks are ~100ms, too slow for smooth knobs)
# it also gets a JSON state (view, the 8 knob parameters, their tracks' meters, touched knob)
# so it can draw faders and knobs instead of text.
MCU_DISPLAY_HEADER = (0xF0, 0x00, 0x00, 0x66, 0x17, 0x12)
SCREEN_BRIDGE_ADDRESS = (Protocolo.HOST, Config.SCREEN_BRIDGE_PORT)
# Every JSON message carries the protocol version (Protocolo.VERSION), so the screens can tell when they and the
# script come from different installs
SCREEN_BRIDGE_MODE_VDJ = json.dumps({"v": Protocolo.VERSION, "type": Protocolo.TYPE_MODE, "vdj": True}).encode("ascii")
SCREEN_BRIDGE_INTERVAL_MS = 50
SCREEN_BRIDGE_STALL_SECONDS = 0.5
SCREEN_BRIDGE_RESEND_TICKS = 20  # display lines are resent about once per second (at 20 FPS)
KNOB_COUNT = 8
# Knob touch (CC 10-17, MIDI channel 2). MUTE + touching a knob in the mixer sends its parameter to zero
# (pan to center); doing it again restores the previous value
KNOB_TOUCH_CCS = tuple((0xB1, 10 + index) for index in range(KNOB_COUNT))
# RESTART + touching a knob sets it to its default value; RESTART alone still toggles the loop, on release
RESTART_BUTTON = (0xB1, 53)
SOLO_BUTTON = (0xB1, 91)
# EVENTS: a new scene under the cursor's, the cursor's clip stopped, the cursor moved there (in every view; its old
# note selection / erase functions are gone)
NEW_SCENE_BUTTON = (0xB1, 87)
ERASE_DOUBLE_TOUCH_SECONDS = 0.4
MIXER_DISPLAY_MODE = "default"
# ARRANGER shows Live's Session view and the clip grid on the Maschine's screens (both screens: 4 tracks each);
# it stays on until another view button (VIEW_BUTTONS) is pressed. Its LED shows it.
SESSION_VIEW_BUTTON = (0xB1, 36)
SESSION_DISPLAY_MODE = "session"
# VARIATION (NAVIGATE) deletes a clip, for a bad take (Live's undo brings it back): in the session view the one under
# the cursor, in the other views the last clip recorded
DELETE_CLIP_BUTTON = (0xB1, 88)
# Session view, encoder in its default mode (like Push): turning or tilting up / down moves the selected clip slot
# one scene, tilting left / right one track, always inside the grid on the screens (it doesn't move);
# with SHIFT they move the grid instead; pushing fires the selected clip slot
SESSION_NAV_TURN = (0xB1, 7)
SESSION_NAV_PUSH = (0xB1, 8)
SESSION_NAV_TILTS = {(0xB1, 30): (0, -1), (0xB1, 31): (1, 0), (0xB1, 32): (0, 1), (0xB1, 33): (-1, 0)}  # (track, scene)
ENCODER_DEFAULT_MODE = "default"
SESSION_GRID_TRACKS = 8
SESSION_GRID_SCENES = 4
RECORDED_CHECK_SECONDS = 0.1  # how often the tracks are looked at for a recording that started or ended
SESSION_GRID_STEP = 4  # the grid on the screens moves sideways in steps of 4 tracks
BROWSER_DISPLAY_MODE = "browser"
BROWSER_BRIDGE_ITEMS = 12  # items sent on each side of the selected one
TEMPO_SCREEN_RANGE = (60.0, 200.0)  # BPM range of the tempo bar on the screens
# PAD MODE, KEYBOARD, CHORDS and STEP select VirtualDJ's pad page, so they follow the pads while locked
PAD_PAGE_BUTTONS = ((0xB1, 81), (0xB1, 82), (0xB1, 83), (0xB1, 84))
# Buttons 1-4 above the screen (notes 0-3, channel 2) belong to VirtualDJ only (stems KICK / HATS of each deck):
# Ableton never uses them, in any mode, and never drives their LEDs
VDJ_ONLY_CHANNEL = 1
# CHANNEL, PLUGIN, ARRANGER, MIXER, BROWSER, SAMPLING, FILE, SETTINGS: any view button turns VOLUME / SWING / TEMPO
# off, in Ableton and in VirtualDJ mode (the VirtualDJ mapping does the same with its own encoder mode)
VIEW_BUTTONS = tuple((0xB1, cc) for cc in range(34, 42))
VDJ_ONLY_NOTES = range(0, 4)
# PITCH, MOD, PERFORM: NOTES (note repeat rate selector on the group buttons) turns off when one of them is pressed
TOUCHSTRIP_MODE_BUTTONS = ((0xB1, 49), (0xB1, 50), (0xB1, 51))

def _track_flag(track, name):
    # Live raises RuntimeError (not AttributeError) for mute / solo on the Main track, so getattr's default is not enough
    try:
        return bool(getattr(track, name))
    except Exception:
        return False

class CustomTargetTrackComponent(TargetTrackComponent):
        
    def _target_clip_from_session(self):
        slot_index = scene_index()
        if slot_index < len(self._target_track.clip_slots):
            clip_slot = self._target_track.clip_slots[slot_index]
        else:
            clip_slot = None

        self._on_clip_slot_state_changed.subject = clip_slot
        if clip_slot:
            if clip_slot.has_clip:
                return clip_slot.clip
    
    @listens("has_clip")
    def _on_clip_slot_state_changed(self):
        self._update_target_clip()


class Specification(ControlSurfaceSpecification):
    elements_type = ControlElements
    control_surface_skin = MaschineSkin
    display_specification = MaschineDisplay if Config.LCD_ENABLED else None
    num_scenes = 4
    num_tracks = 4
    include_returns = True
    include_master = True
    include_auto_arming = True
    target_track_component_type = CustomTargetTrackComponent
    continuous_parameter_sensitivity = 2.0
    quantized_parameter_sensitivity = 0.2
    identity_response_id_bytes = [0x00, 0x00, 0x00]
    create_mappings_function = create_mappings
    recording_method_type = FixedLengthRecordingMethod
    feedback_channels = [DEFAULT_NOTE_TRANSLATION_CHANNEL, DEFAULT_SIMPLER_TRANSLATION_CHANNEL, DEFAULT_DRUM_TRANSLATION_CHANNEL]
    component_map = {
        "Pageable_Background": PageableBackgroundComponent,
        "Settings": SettingsComponent,
        "Transport": CustomTransportComponent,
        "Session": partial(SessionComponent, clip_slot_component_type = CustomClipSlotComponent),
        "Encoder_Mode_Control": EncoderModeControlComponent,
        "Group_Button_Mode_Control": GroupButtonModeControlComponent,
        "View_Based_Recording": partial(CustomViewBasedRecordingComponent, recording_method_type = recording_method_type),
        "Browser": BrowserComponent,
        "Clip_Editor": ClipEditorComponent,
        "Selected_Parameter": SelectedParameterControlComponent,
        "Scale_System": ScaleSystemComponent,
        "Velocity_Levels": VelocityLevelsComponent,
        "Note_Repeat": NoteRepeatComponent,
        "Sliced_Simpler": CustomSlicedSimplerComponent,
        "Drum_Group": CustomDrumGroupComponent,
        "Clip_Actions": CustomClipActionsComponent,
        "Groove_Pool": GroovePoolComponent,
        "Master_Volume": MasterVolumeComponent,
        "Cue_Volume": CueVolumeComponent,
        "Maschine_Playable": MaschinePlayableComponent,
        "Misc_Control": MiscControlComponent,
        # Does nothing: the pad mode used while the pads are locked to VirtualDJ
        "Pad_Lock": Component,
        "Device_Navigation": CustomDeviceNavigationComponent,
        "Session_Volume": SessionVolumeComponent,
        "Session_Zones": SessionZonesComponent,
    }
    parameter_bank_definitions = CUSTOM_BANK_DEFINITIONS

class BypassIdentification(IdentificationComponent):
    def request_identity(self):
        logger.info("Request identity")
        self.is_identified = False
        sleep(0.01)
        self.is_identified = True

DEFAULT_MODE = "default"
KEYBOARD_MODE = "keyboard"
DRUMRACK_MODE = "drum_rack"
SIMPLER_MODE = "simpler"

CUSTOM_GRID_RESOLUTIONS = (
    GridResolution("1/4", 1.0, GridQuantization.g_quarter, False),
    GridResolution("1/4t", 0.6666666666666666, GridQuantization.g_quarter, True),
    GridResolution("1/8", 0.5, GridQuantization.g_eighth, False),
    GridResolution("1/8t", 0.3333333333333333, GridQuantization.g_eighth, True),
    GridResolution("1/16", 0.25, GridQuantization.g_sixteenth, False),
#    GridResolution("1/16t", 0.16666666666666666, GridQuantization.g_sixteenth, True),
#    GridResolution("1/32", 0.125, GridQuantization.g_thirtysecond, False),
#    GridResolution("1/32t", 0.08333333333333333, GridQuantization.g_thirtysecond, True),
)
GRID_DEFAULT_INDEX = 4

class CustomMaschineMK3(ControlSurface):
    _grid_resolution = None
    _sequencer_clip = None
    _pad_mode = None
    _step_sequencer = None
    _playable_mode_list = (KEYBOARD_MODE, DRUMRACK_MODE, SIMPLER_MODE)
    _provider_list = {
        KEYBOARD_MODE: "Maschine_Playable",
        DRUMRACK_MODE: "Drum_Group",
        SIMPLER_MODE: "Sliced_Simpler"
    }
    _current_drum_group = None
    _current_sliced_simpler = None
    _display_mode = None
    _settings = None
    _vdj_mode = False
    _standby = Config.START_IN_STANDBY
    _shift_down = False
    _pad_lock = False
    _swallow_lock_release = False
    _pad_mode_before_lock = None
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
    _restart_held = False
    _restart_used = False
    _follow_held = False
    _follow_used = False
    _swallow_tempo_release = False
    _scene_down = False
    _erase_touch = (None, 0.0)  # (knob index, time) of the last ERASE + knob touch
    _browser_bridge_key = None  # browser folder whose items are cached for the screens
    _browser_bridge_items = ()
    _browser_bridge_parent = None
    _session_block_start = 0  # first track of the session grid on the screens
    _recorded_checked = 0.0
    _recording_slots = ()  # clip slots recording right now
    _last_recorded = None  # clip slot of the last recording that ended
    _logged_state = None  # last value logged of each thing _log_state_changes follows
    _logged_errors = {}  # key -> (text, time) of the last error logged
    _ring_offsets_seen = None  # (track, scene) offsets of the session ring at the last tick
    _screen_bridge_error_logged = False

    def __init__(self, *a, **k):
        # Settings must be loaded before initialization
        self._settings = SettingsRepository()
        # The display is drawn during initialization, so the bridge must exist before it
        self._init_screen_bridge()
        self._init_specification()
        super().__init__(Specification, *a, **k)
        #logger.info(dir(self._c_instance))

        #self.register_slot(self.elements.variation, self._on_update_triggered, "is_pressed")
        self.register_slot(self.elements.keyboard, self._on_playable_mode_selected, "is_pressed")
        self.register_slot(self.component_map["Pad_Modes"], self._on_pad_mode_changed, "selected_mode")
        self.register_slot(self.component_map["Display_Modes"], self._on_display_mode_changed, "selected_mode")
        if "TouchStrip_Modes" in self.component_map:
            self.register_slot(self.component_map["TouchStrip_Modes"], self._on_touchstrip_mode_changed, "selected_mode")
        self.schedule_message(1, self._init_touchstrip)
    
    def _init_specification(self):
        Specification.component_map["Device"] = partial(
            CustomDeviceComponent,
            device_decorator_factory = CustomDeviceDecoratorFactory(),
            bank_definitions = Specification.parameter_bank_definitions,
            bank_size = Specification.parameter_bank_size,
            continuous_parameter_sensitivity = Specification.continuous_parameter_sensitivity,
            quantized_parameter_sensitivity = Specification.quantized_parameter_sensitivity)

        pad_row_notes = list(range(60, 76, 4))
        if self._settings.get_value("sequencer_style") == "Push":
            pad_row_notes = pad_row_notes[::-1]
        playhead_notes = [base_note + offset for base_note, offset in product(pad_row_notes, range(4))]
        triplet_playhead_notes = [base_note + offset for base_note, offset in product(pad_row_notes, range(3))]

        Specification.component_map["Step_Sequence"] = partial(
            CustomStepSequenceComponent,
            note_editor_component_type = CustomNoteEditorComponent,
            playhead_notes = tuple(playhead_notes),
            playhead_triplet_notes = tuple(triplet_playhead_notes),
            playhead_channels = [1])
        
        mixer_mode = self._settings.get_value("mixer_mode")
        if mixer_mode == "4Track":
            mixer_component = CustomMixerComponent
        elif mixer_mode == "8Track":
            mixer_component = MaschineMixerComponent

        Specification.component_map["Mixer"] = mixer_component

    # Sometimes pad leds couldn't update correctly
    # I don't know why this happens now, push "CHANNEL" button for refresh state
    def _on_update_triggered(self):
        if self.elements.variation.is_pressed:
            logger.info("Display update triggered")
            self.refresh_state()

    def _do_send_midi(self, midi_event_bytes):
        # Standby: nothing reaches the Maschine's LEDs or display (_blank_hardware writes its own zeros)
        if self._standby:
            return True
        # FOLLOW's LED shows Ableton Link (sent by _update_link_led only)
        if tuple(midi_event_bytes[:2]) == LINK_BUTTON:
            return True
        # VirtualDJ owns LEDs and display while VirtualDJ mode is active, except Ableton's own transport buttons
        if self._vdj_mode and tuple(midi_event_bytes[:2]) not in ABLETON_ALWAYS_BUTTONS:
            return True
        if self._is_vdj_only(midi_event_bytes):
            return True
        # Pads locked to VirtualDJ keep VirtualDJ's colors, page button LEDs and the lit LOCK button
        if self._pad_lock and self._is_pad_section(midi_event_bytes, include_lock = True):
            return True
        logger.debug(f"_do_send_midi {midi_event_bytes}")
        super()._do_send_midi(midi_event_bytes)
        self._copy_to_screen_bridge(midi_event_bytes)
        # Insert super short wait between each send to make sure LED feedback correctly.
        # During development, I encountered problem some pads / buttons LEDs not change to current mode value.
        # After several investigations, I found a wait inserted on old Maschine Ableton script.
        # Maybe 500us or more wait prevent issue.
        # This wait doesn't affect response speed, unless if you can play pads at 999 BPM...
        sleep(0.0005)

    # Live may deliver incoming MIDI one message at a time or in chunks, so filter both entry points
    def receive_midi(self, midi_bytes):
        if self._accept_midi(midi_bytes):
            super().receive_midi(midi_bytes)

    def receive_midi_chunk(self, midi_chunk):
        accepted = tuple(midi_bytes for midi_bytes in midi_chunk if self._accept_midi(midi_bytes))
        if accepted:
            super().receive_midi_chunk(accepted)

    def _accept_midi(self, midi_bytes):
        midi_bytes = tuple(midi_bytes)
        if self._is_vdj_only(midi_bytes):
            return False
        is_cc = len(midi_bytes) == 3
        # SHIFT's state, tracked here as well: SHIFT + CHANNEL must not depend on the framework having seen it
        if midi_bytes[:4] == SHIFT_SYSEX_PREFIX and len(midi_bytes) > 12:
            self._shift_down = midi_bytes[-2] > 0
        elif is_cc and midi_bytes[:2] == SHIFT_BUTTON:
            self._shift_down = midi_bytes[2] > 0
        elif is_cc and midi_bytes[:2] == SCENE_BUTTON:
            self._scene_down = midi_bytes[2] > 0  # tracked here too; SCENE still reaches the framework (SCENE + pad)
        if is_cc and midi_bytes[0] == 0xB1 and midi_bytes[2] > 0 and midi_bytes[1] in BUTTON_NAMES:
            self._log(f"button {BUTTON_NAMES[midi_bytes[1]]} pressed (shift = {self._shift_down}, "
                      f"standby = {self._standby}, vdj = {self._vdj_mode})")
        if is_cc and not self._vdj_mode and not self._standby:
            if midi_bytes[:2] == SESSION_NAV_PUSH and self._scene_down:
                if midi_bytes[2] > 0:
                    self._launch_cursor_scene()
                return False
            if midi_bytes[:2] == PATTERN_BUTTON:
                if midi_bytes[2] > 0:
                    self._capture_scene()
                return False
        if is_cc and not self._standby:
            # Also in VirtualDJ mode: the tempo view opened from there controls Ableton's tempo the same way
            # (VirtualDJ's mapping ignores the encoder in its encoder mode 3 and the driver draws the view)
            if (midi_bytes[:2] == ENCODER_TURN_BUTTON and not self._shift_down and self._encoder_tempo_mode()):
                self._turn_tempo(midi_bytes[2])
                return False
            if midi_bytes[:2] == TEMPO_BUTTON:
                if midi_bytes[2] > 0 and self._shift_down:
                    # SHIFT + TEMPO: sync with VirtualDJ, in any view, leaving the view as it is; the press never
                    # reaches the encoder mode component, which would toggle the tempo view
                    self._swallow_tempo_release = True
                    self._sync_tempo_with_virtualdj()
                    return False
                if midi_bytes[2] == 0 and self._swallow_tempo_release:
                    self._swallow_tempo_release = False
                    return False
        if is_cc and midi_bytes[:2] == MACRO_BUTTON and midi_bytes[2] > 0 and self._shift_down:
            self._restart_screens()
            return False
        if self._standby:
            # Everything is ignored, except SHIFT's state and the buttons that wake the Maschine
            if midi_bytes[:4] == SHIFT_SYSEX_PREFIX:
                return True
            if is_cc and midi_bytes[2] > 0:
                key = midi_bytes[:2]
                if key == VDJ_ENTER_BUTTON:
                    self._set_standby(False)
                    self._set_vdj_mode(True)
                elif key in STANDBY_WAKE_BUTTONS:
                    self._set_standby(False)
                    return key != STANDBY_BUTTON  # MIXER / PLUGIN also go on to select their view
            return False
        if (is_cc and midi_bytes[:2] == STANDBY_BUTTON and midi_bytes[2] > 0
                and (self._shift_down or self.elements.shift.is_pressed)):
            self._set_standby(True)
            return False
        # "SAMPLING" never reaches Ableton, it's reserved for entering VirtualDJ mode
        if is_cc and midi_bytes[:2] == VDJ_ENTER_BUTTON:
            if midi_bytes[2] > 0:
                # A view button too: VOLUME / SWING / TEMPO off
                with self.component_guard():
                    self.component_map["Encoder_Mode_Control"].reset_selected_mode()
                if not self._vdj_mode:
                    self._set_vdj_mode(True)
            return False

        # FOLLOW is a modifier only: FOLLOW + knob launches the clip of that knob's track in the cursor's scene.
        # It no longer toggles Ableton Link (Link is still on / off from Live itself)
        if is_cc and midi_bytes[:2] == LINK_BUTTON and not self._vdj_mode:
            if midi_bytes[2] > 0:
                self._follow_held, self._follow_used = True, False
            else:
                self._follow_held = False
            return False

        # RESTART + SOLO (in either order): every track out of the prelisten / solo
        if (is_cc and midi_bytes[2] > 0 and not self._vdj_mode
                and ((midi_bytes[:2] == SOLO_BUTTON and self._restart_held)
                     or (midi_bytes[:2] == RESTART_BUTTON and self.elements.solo.is_pressed))):
            self._restart_held, self._restart_used = midi_bytes[:2] == RESTART_BUTTON or self._restart_held, True
            self._clear_prelisten()
            return False

        if is_cc and midi_bytes[:2] == PAD_LOCK_BUTTON:
            if midi_bytes[2] > 0:
                if self._vdj_mode:
                    self._pad_lock = not self._pad_lock
                    self._c_instance.log_message(f"CustomMaschineMK3: pad lock = {self._pad_lock}")
                    return False
                if self._pad_lock:
                    # In Ableton, LOCK only releases the pads; the press (and its release) never reach Ableton
                    self._set_pad_lock(False)
                    self._swallow_lock_release = True
                    return False
            elif self._swallow_lock_release:
                self._swallow_lock_release = False
                return False

        # RESTART is also a modifier: its loop on / off happens on release, only if no knob was touched meanwhile
        if is_cc and midi_bytes[:2] == RESTART_BUTTON and not self._vdj_mode:
            if midi_bytes[2] > 0:
                self._restart_held, self._restart_used = True, False
                if self._shift_down or self.elements.shift.is_pressed:
                    # SHIFT + RESTART: every volume in the mixer back to its default (not the loop toggle)
                    self._restart_used = True
                    self._reset_all_volumes()
            else:
                if self._restart_held and not self._restart_used:
                    self.song.loop = not self.song.loop
                self._restart_held = False
            return False

        if is_cc and midi_bytes[:2] in KNOB_TOUCH_CCS and midi_bytes[2] > 0 and not self._vdj_mode:
            index = KNOB_TOUCH_CCS.index(midi_bytes[:2])
            volume_view = self.component_map["Display_Modes"].selected_mode in (MIXER_DISPLAY_MODE, SESSION_DISPLAY_MODE)
            if self._restart_held:
                # RESTART + knob: default value (device parameter's default, mixer volume to 0 dB...)
                self._restart_used = True
                self._set_knob_parameter(index, default = True)
            elif self.elements.erase.is_pressed and volume_view:
                # ERASE + double touch on a knob in the mixer / session view: to zero (volume to -inf, pan to
                # center). Double, so it can't happen by accident
                now = perf_counter()
                last_index, last_time = self._erase_touch
                if last_index == index and now - last_time <= ERASE_DOUBLE_TOUCH_SECONDS:
                    self._set_knob_parameter(index, default = False)
                    self._erase_touch = (None, 0.0)
                else:
                    self._erase_touch = (index, now)
            elif self.elements.mute.is_pressed and volume_view:
                # MUTE + knob: stop the clip playing on that knob's track
                self._stop_knob_track_clip(index)
            elif self.elements.solo.is_pressed and volume_view:
                # SOLO + knob: that knob's track to the prelisten (solo / cue, as Live's Solo / Cue switch says)
                self._toggle_knob_track_prelisten(index)
            elif self._follow_held and volume_view:
                # FOLLOW + knob: launch the clip of that knob's track in the scene under the cursor
                self._follow_used = True
                self._launch_knob_track_clip(index)

        if (is_cc and not self._vdj_mode
                and (self._session_view or self.component_map["Display_Modes"].selected_mode == MIXER_DISPLAY_MODE)
                and (midi_bytes[:2] in (SESSION_NAV_TURN, SESSION_NAV_PUSH) or midi_bytes[:2] in SESSION_NAV_TILTS)
                and self.component_map["Encoder_Modes"].selected_mode == ENCODER_DEFAULT_MODE):
            self._handle_session_navigation(midi_bytes)
            return False

        if (is_cc and midi_bytes[:2] in (LEFT_BUTTON, RIGHT_BUTTON) and not self._vdj_mode
                and self.component_map["Display_Modes"].selected_mode == MIXER_DISPLAY_MODE
                and not self.elements.macro.is_pressed and not self.elements.plugin.is_pressed):
            # In the mixer, left / right change the mixer page: volume <-> pan <-> sends (FXs)
            # Letting the press through to MaschineMixerComponent.prev_parameter_button / next_parameter_button
            return True

        if is_cc and midi_bytes[:2] == NEW_SCENE_BUTTON and not self._vdj_mode:
            if midi_bytes[2] > 0:
                self._new_scene_below_cursor()
            return False

        if is_cc and midi_bytes[:2] == DELETE_CLIP_BUTTON and not self._vdj_mode:
            if midi_bytes[2] > 0:
                self._delete_clip()
            return False

        if is_cc and (midi_bytes[:2] in VIEW_BUTTONS or midi_bytes[:2] in PAD_PAGE_BUTTONS) and midi_bytes[2] > 0:
            # Also when the view doesn't change (e.g. MIXER while already in the mixer); the pad pages
            # (KEYBOARD, PAD MODE, CHORDS, STEP) too, like in the VirtualDJ mapping
            with self.component_guard():
                self.component_map["Encoder_Mode_Control"].reset_selected_mode()

        # ARRANGER enters the session view; the other view buttons leave it (they select their own display mode)
        if is_cc and midi_bytes[:2] == SESSION_VIEW_BUTTON:
            if midi_bytes[2] > 0:
                if self._vdj_mode:
                    self._set_vdj_mode(False)
                self._show_session_view()
            return False

        if is_cc and midi_bytes[:2] in TOUCHSTRIP_MODE_BUTTONS and midi_bytes[2] > 0 and not self._vdj_mode:
            notes = self.component_map["Group_Button_Mode_Control"]
            if notes.get_note_repeat_selector_state():
                with self.component_guard():
                    notes.set_note_repeat_selector_state(False)

        if self._vdj_mode:
            if is_cc and midi_bytes[:2] in VDJ_EXIT_BUTTONS and midi_bytes[2] > 0:
                # Leave VirtualDJ mode and let the press through, so it selects mixer / device mode as usual
                self._set_vdj_mode(False)
                return True
            # PLAY / STOP (and SHIFT, for SHIFT + STOP) keep driving Ableton's transport
            if midi_bytes[:4] == SHIFT_SYSEX_PREFIX:
                return True
            return is_cc and (midi_bytes[:2] in ABLETON_ALWAYS_BUTTONS or midi_bytes[:2] in SHARED_ENCODER_MODE_BUTTONS)

        if self._pad_lock and self._is_pad_section(midi_bytes):
            return False

        return True

    @staticmethod
    def _is_vdj_only(midi_bytes):
        # Note on / off / poly pressure of the VirtualDJ-only buttons
        midi_bytes = tuple(midi_bytes)
        return (len(midi_bytes) == 3 and midi_bytes[0] & 0xF0 in (0x80, 0x90, 0xA0)
                and midi_bytes[0] & 0x0F == VDJ_ONLY_CHANNEL and midi_bytes[1] in VDJ_ONLY_NOTES)

    @staticmethod
    def _is_pad_section(midi_bytes, include_lock = False):
        # The 16 pads (note on / off / poly pressure on any channel), the pad page buttons, the group buttons A-H
        # and the touch strip: what the pad lock gives to VirtualDJ
        midi_bytes = tuple(midi_bytes)
        if len(midi_bytes) != 3:
            return False
        if midi_bytes[0] & 0xF0 in (0x80, 0x90, 0xA0) and midi_bytes[1] in PAD_NOTES:
            return True
        if midi_bytes[0] & 0xF0 == 0xE0:  # the touch strip (pitch bend): movement, and its LEDs on the way out
            return True
        if midi_bytes[0] == 0xB1 and midi_bytes[1] in GROUP_BUTTON_CCS:  # A-H
            return True
        return midi_bytes[:2] in PAD_PAGE_BUTTONS or (include_lock and midi_bytes[:2] == PAD_LOCK_BUTTON)

    def build_midi_map(self, midi_map_handle):
        script_handle = self._c_instance.handle()
        if not (self._vdj_mode or self._standby):
            super().build_midi_map(midi_map_handle)
            if self._pad_lock:
                # Pads locked to VirtualDJ: forward their notes and page buttons to the script so receive_midi
                # drops them, instead of Live playing the notes on an armed track
                for note in PAD_NOTES:
                    Live.MidiMap.forward_midi_note(script_handle, midi_map_handle, 0, note)
                for _, cc in PAD_PAGE_BUTTONS:
                    Live.MidiMap.forward_midi_cc(script_handle, midi_map_handle, 1, cc)
                # The group buttons and the touch strip stay with VirtualDJ too (its crossfader, effects and PFL)
                for cc in GROUP_BUTTON_CCS:
                    Live.MidiMap.forward_midi_cc(script_handle, midi_map_handle, 1, cc)
                for channel in (0, 1):
                    Live.MidiMap.forward_midi_pitchbend(script_handle, midi_map_handle, channel)
            return

        # Knobs and touch strip are normally mapped by Live directly to parameters, bypassing receive_midi.
        # In VirtualDJ mode, forward every message on Maschine's channels to the script instead,
        # so receive_midi can drop them and nothing reaches Live (not even armed tracks).
        for channel in (0, 1):
            Live.MidiMap.forward_midi_pitchbend(script_handle, midi_map_handle, channel)
            for identifier in range(128):
                Live.MidiMap.forward_midi_cc(script_handle, midi_map_handle, channel, identifier)
                Live.MidiMap.forward_midi_note(script_handle, midi_map_handle, channel, identifier)

    def _log(self, message):
        # Always written to Live's Log.txt, regardless of Config.LOGGING
        self._c_instance.log_message(f"CustomMaschineMK3: {message}")

    def _log_state_changes(self):
        # One line for every change of what the Maschine is doing: views, modes, standby, the session ring, the
        # selected track, the locked track and device. Called from the screen bridge tick (~30 times a second)
        try:
            ring = getattr(self, "_session_ring", None)
            view = self.song.view
            target = self.component_map["Target_Track"]
            device = getattr(self.component_map["Device"], "device", None)
            if callable(device):
                device = device()
            values = {
                "display view": self.component_map["Display_Modes"].selected_mode,
                "encoder mode": self.component_map["Encoder_Modes"].selected_mode,
                "pad mode": self.component_map["Pad_Modes"].selected_mode,
                "standby": self._standby,
                "vdj mode": self._vdj_mode,
                "pad lock": self._pad_lock,
                "session ring (track, scene)": (ring.track_offset, ring.scene_offset) if ring is not None else None,
                "selected track": liveobj_name(view.selected_track) if liveobj_valid(view.selected_track) else None,
                "selected scene": liveobj_name(view.selected_scene) if liveobj_valid(view.selected_scene) else None,
                "target track": liveobj_name(target.target_track) if liveobj_valid(target.target_track) else None,
                "track locked": target.is_locked_to_track,
                "device": liveobj_name(device) if liveobj_valid(device) else None,
            }
        except Exception:
            self._log_error_once("state log", traceback.format_exc())
            return
        if self._logged_state is None:
            self._logged_state = {}
        for key, value in values.items():
            if key in self._logged_state and self._logged_state[key] != value:
                self._log(f"{key}: {self._logged_state[key]} -> {value}")
            self._logged_state[key] = value

    def _log_error_once(self, key, text):
        # The same error is logged again only after a minute (it can repeat at every tick)
        now = perf_counter()
        last_text, last_time = self._logged_errors.get(key, (None, 0.0))
        if text != last_text or now - last_time > 60.0:
            self._logged_errors[key] = (text, now)
            self._log(f"ERROR in {key}:\n{text}")

    def _set_standby(self, enabled):
        if enabled == self._standby:
            return
        self._c_instance.log_message(f"CustomMaschineMK3: standby = {enabled}")
        if enabled:
            # VirtualDJ's mapping also leaves its mode with SHIFT + CHANNEL
            self._vdj_mode = False
            self._pad_lock = False
            self._sync_pad_lock_mode()
            self._standby = True
            self.request_rebuild_midi_map()
            self._blank_hardware()
        else:
            self._standby = False
            self.request_rebuild_midi_map()
            self._redisplay()
            self.schedule_message(VDJ_REFRESH_DELAY, self._refresh_after_vdj_mode)

    def _blank_hardware(self):
        # Pads, buttons, the touch strip and the display lines off (written past the standby filter)
        for note in PAD_NOTES:
            self._send_blank((0x90, note, 0))
        for note in STANDBY_LED_NOTES:
            self._send_blank((0x91, note, 0))
        for cc in STANDBY_LED_CCS:
            self._send_blank((0xB1, cc, 0))
        self._send_blank((0xE0, 0x00, 0x00))
        for line in range(4):
            self._send_blank(make_display_sysex_message(line, (ord(" "),) * 28))

    def _send_blank(self, midi_event_bytes):
        try:
            super()._do_send_midi(midi_event_bytes)
            sleep(0.0005)
        except Exception as error:
            logger.debug(f"blank failed: {error!r}")

    def _set_vdj_mode(self, enabled):
        # Always written to Live's Log.txt, regardless of Config.LOGGING
        self._c_instance.log_message(f"CustomMaschineMK3: VirtualDJ mode = {enabled}")
        if enabled:
            super()._do_send_midi((SESSION_VIEW_BUTTON[0], SESSION_VIEW_BUTTON[1], 0))
        self._vdj_mode = enabled
        self._sync_pad_lock_mode()
        self.request_rebuild_midi_map()
        if not enabled:
            self._redisplay()
            self.schedule_message(VDJ_REFRESH_DELAY, self._refresh_after_vdj_mode)

    def _set_pad_lock(self, enabled):
        self._c_instance.log_message(f"CustomMaschineMK3: pad lock = {enabled}")
        self._pad_lock = enabled
        self._sync_pad_lock_mode()
        self.request_rebuild_midi_map()
        if not enabled:
            # Pads are Ableton's again: redraw their LEDs
            self.schedule_message(VDJ_REFRESH_DELAY, self._refresh_after_vdj_mode)

    def _sync_pad_lock_mode(self):
        # While the pads are locked to VirtualDJ in Ableton, no pad mode (session, keyboard, chords, step...) uses them
        pad_modes = self.component_map["Pad_Modes"]
        locked = self._pad_lock and not self._vdj_mode
        with self.component_guard():
            if locked and pad_modes.selected_mode != PAD_LOCK_MODE:
                self._pad_mode_before_lock = pad_modes.selected_mode
                pad_modes.selected_mode = PAD_LOCK_MODE
            elif not locked and pad_modes.selected_mode == PAD_LOCK_MODE:
                pad_modes.selected_mode = self._pad_mode_before_lock or DEFAULT_MODE

    def _update_link_led(self):
        if self._vdj_mode or self._standby:
            return
        # FOLLOW's LED stays off: it doesn't show Ableton Link any more
        super()._do_send_midi((LINK_BUTTON[0], LINK_BUTTON[1], 0))

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

    def _reset_all_volumes(self):
        # Every track and return back to its volume's default (0 dB); the master volume is left alone
        count = 0
        for track in list(self.song.tracks) + list(self.song.return_tracks):
            volume = track.mixer_device.volume
            volume.value = volume.default_value
            count += 1
        self._c_instance.show_message(f"Volumes reset to default ({count} tracks)")
        self._c_instance.log_message(f"CustomMaschineMK3: {count} volumes reset to default")

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
        # The track of a knob is the owner of the parameter it controls (volume, pan or send of a track). In the
        # device page of the session view the knobs control a device, not a track: nothing to do there
        parameter = self._get_knob_mapped_parameter(index)
        owner = parameter_owner(parameter) if liveobj_valid(parameter) else None
        if not isinstance(owner, Live.Track.Track):
            self._log(f"{what} + knob {index + 1}: that knob doesn't control a track")
            self._c_instance.show_message("That knob doesn't control a track")
            return None
        return owner

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
                self._log_error_once("protocol version", f"the screens driver sends protocol v{latest.get('v')}, "
                                     f"the script expects v{Protocolo.VERSION}: install both from the same branch")
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
                self._c_instance.log_message(f"CustomMaschineMK3: screen bridge timer running (repeat = {self._screen_bridge_timer_repeats})")
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
                    self._c_instance.log_message("CustomMaschineMK3: screen bridge timer not firing, using ~100ms ticks")
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
            self._send_to_screen_bridge(SCREEN_BRIDGE_MODE_VDJ)
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
            self._c_instance.log_message(f"CustomMaschineMK3: screen bridge timer failed ({error!r}), using ~100ms ticks")
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

    def _redisplay(self):
        # Clearing the send cache makes each display line re-send its last content right away (only 4 sysex messages)
        for line in range(4):
            display_line = getattr(self.elements, f"display_line_{line}", None)
            if display_line is not None:
                display_line.clear_send_cache()

    def _refresh_after_vdj_mode(self):
        if not self._vdj_mode:
            with self.component_guard():
                self.refresh_state()
            self._update_link_led()
            self._update_session_view_led()
            modes = self.component_map.get("TouchStrip_Modes")
            if modes is None or getattr(modes, "selected_mode", "pitch") == "pitch":
                self._do_send_midi((0xE0, 0x00, 0x40))

    # Session ring highlight is enabled only if hardware is identified by identity request
    # But maschine didn't respond to this message, so bypass identification process
    def _create_identification(self, specification):
        #return super()._create_identification(specification)
        identification = BypassIdentification(
            identity_request = specification.identity_request,
            identity_request_delay = specification.identity_request_delay,
            identity_response_id_bytes = specification.identity_response_id_bytes,
            custom_identity_response = specification.custom_identity_response)
        self._ControlSurface__on_is_identified_changed.subject = identification

        return identification

    @lazy_attribute
    def _create_grid_resolution(self):
        self._grid_resolution = GridResolutionComponent(resolutions = CUSTOM_GRID_RESOLUTIONS, default_index = GRID_DEFAULT_INDEX)
        self._grid_resolution.resolution_buttons.control_count = len(CUSTOM_GRID_RESOLUTIONS)
        return self._grid_resolution

    @lazy_attribute
    def _create_sequencer_clip(self):
        self._sequencer_clip = SequencerClip()
        return self._sequencer_clip
        
    @lazy_attribute
    def _create_blinker(self):
        self._blinker = LEDBlinker()
        return self._blinker
    
    def _get_knob_mapped_parameter(self, index):
        if index >= 0 and index < len(self.elements.knobs_raw):
            return self.elements.knobs_raw[index].mapped_parameter()

    def _get_additional_dependencies(self):
        # Register objects to DI container
        # Dict key name came from @depends decorator of each component classes
        # Registered components pass to appropriate components on demand
        inject_dict = {
            "grid_resolution": lambda: self._create_grid_resolution,
            "sequencer_clip": lambda: self._create_sequencer_clip,
            "note_repeat": const(self._c_instance.note_repeat),
            "velocity_levels": const(self._c_instance.velocity_levels),
            "get_knob_mapped_parameter": const(self._get_knob_mapped_parameter),
            "settings": const(self._settings),
            "blinker": lambda: self._create_blinker,
        }
        
        return inject_dict

    def setup(self):
        super().setup()
        self.set_can_update_controlled_track(True)
        self.set_can_auto_arm(True)
        with self.component_guard():
            self.component_map["Pad_Modes"].selected_mode = DEFAULT_MODE
            self.component_map["Maschine_Playable"].set_scale_system(self.component_map["Scale_System"])
            self.component_map["Step_Sequence"]._note_editor.set_velocity_levels(self.component_map["Velocity_Levels"])
            self.component_map["Clip_Editor"].set_step_sequence(self.component_map["Step_Sequence"])
            self.component_map["Session_Volume"].set_device_component(self.component_map["Device"])
            encoder_mode_control = self.component_map["Encoder_Mode_Control"]
            encoder_mode_control.set_encoder_modes(self.component_map["Encoder_Modes"])
            display_mode = self.component_map["Display_Modes"]
            encoder_mode_control.set_display_modes(display_mode)
            self.component_map["Browser"].set_display_modes(display_mode)
            group_button_control = self.component_map["Group_Button_Mode_Control"]
            group_button_control.set_pad_modes(self.component_map["Pad_Modes"])
            group_button_control.set_group_button_modes(self.component_map["Group_Button_Modes"])
            self.component_map["Note_Repeat"].set_group_button_control(group_button_control)
        self._start_screen_bridge()
        if self._standby:
            self.request_rebuild_midi_map()
            self._blank_hardware()
        self._log(f"script loaded (standby = {self._standby}, mixer mode = {self._settings.get_value('mixer_mode')}, "
                  f"screen bridge = {SCREEN_BRIDGE_ADDRESS})")

    def disconnect(self):
        self._log("script disconnected")
        super().disconnect()

        # Save settings
        self._settings.save()

        # Clear display
        for line in range(4):
            message = make_display_sysex_message(line, (ord(" "),) * 28)
            self._send_midi(message)
        
        # Clear touchstrip
        self._send_midi((0xE0, 0x00, 0x00))
        # Pads and buttons off too: with Ableton closed the Maschine rests instead of keeping its last lights
        self._standby = True
        self._blank_hardware()

        if self._screen_bridge_timer is not None:
            self._screen_bridge_timer.stop()
            self._screen_bridge_timer = None
        if self._screen_bridge is not None:
            self._screen_bridge.close()
            self._screen_bridge = None
        if self._vdj_tempo_socket is not None:
            self._vdj_tempo_socket.close()
            self._vdj_tempo_socket = None

    def _on_playable_mode_selected(self):
        logger.info(f"keyboard button state = {self.elements.keyboard.is_pressed}")
        if self.elements.keyboard.is_pressed:
            with self.component_guard():
                if liveobj_valid(self._current_drum_group):
                    self._select_playable_mode(DRUMRACK_MODE)
                elif liveobj_valid(self._current_sliced_simpler):
                    self._select_playable_mode(SIMPLER_MODE)
                else:
                    self._select_playable_mode(KEYBOARD_MODE)

    def _init_touchstrip(self):
        if not self._vdj_mode and not self._standby:
            modes = self.component_map.get("TouchStrip_Modes")
            if modes is None or getattr(modes, "selected_mode", "pitch") == "pitch":
                self._do_send_midi((0xE0, 0x00, 0x40))

    def _on_touchstrip_mode_changed(self, *a, **k):
        if not self._vdj_mode and not self._standby:
            modes = self.component_map.get("TouchStrip_Modes")
            mode = getattr(modes, "selected_mode", "pitch") if modes else "pitch"
            if mode == "pitch":
                self._do_send_midi((0xE0, 0x00, 0x40))
            else:
                self._do_send_midi((0xE0, 0x00, 0x00))

    def _on_pad_mode_changed(self, component):
        is_playable_enabled = self.get_pad_mode() in self._playable_mode_list
        state = "On" if is_playable_enabled else "Off"
        self.elements.keyboard.send_value(MaschineSkin[f"DefaultButton.{state}"].midi_value)

    def _on_display_mode_changed(self, component):
        mode = self.component_map["Display_Modes"].selected_mode
        self._update_session_view_led()
        if mode == "browser" and self._display_mode != "browser":
            # Opening the browser starts inside the User Library (the user's folders and its content)
            self.component_map["Browser"].open_in_user_library()
        if self._display_mode == "custom":
            self._refresh_track_buttons_state(mode)
            # self._refresh_task = self._tasks.add(task.sequence(task.wait(0.1), task.run(lambda: self._refresh_upper_button_state(mode))))
        self._display_mode = mode
        if mode == "default":
            return
        elif mode == "device":
            target_view = "Detail/DeviceChain"
        elif mode == "clip":
            target_view = "Detail/Clip"
        else:
            return
        
        if not self.application.view.is_view_visible(target_view):
            self.application.view.show_view(target_view)

        self.application.view.focus_view(target_view)

    def _refresh_track_buttons_state(self, mode):
        # LED state sync failure happens when the display mode switches to another mode from the custom(MIDI mapping) mode
        # Triggering update manually to sync LED state
        # The easiest solution is just calling update(), but it refreshes all components and controls state.
        # I confine the targets to objects that affect this issue to reduce unnecessary processes.
        logger.info("Trigger upper button state update")

        with self.component_guard():
            for button in self.elements.track_buttons_raw:
                button.clear_send_cache()

            if mode == "default":
                self.component_map["Mixer"].update()
            elif mode == "device":
                self.component_map["Device_Navigation"].update()
            elif mode == "clip":
                self.component_map["Clip_Editor"].update()
            elif mode == "browser":
                self.component_map["Browser"].update()
            elif mode == "settings":
                self.component_map["Settings"].update()

    def drum_group_changed(self, drum_group):
        logger.info(f"Drum Group = {drum_group}")
        self._current_drum_group = drum_group

        with self.component_guard():
            update_mode = self.get_pad_mode() in self._playable_mode_list
            if liveobj_valid(drum_group):
                self._select_playable_mode(DRUMRACK_MODE, update_mode)
            elif not liveobj_valid(self._current_sliced_simpler):
                self._select_playable_mode(KEYBOARD_MODE, update_mode)

    def sliced_simpler_changed(self, sliced_simpler):
        logger.info(f"Simpler = {sliced_simpler}")
        self._current_sliced_simpler = sliced_simpler
        
        with self.component_guard():
            update_mode = self.get_pad_mode() in self._playable_mode_list
            if liveobj_valid(sliced_simpler):
                self._select_playable_mode(SIMPLER_MODE, update_mode)
            elif not liveobj_valid(self._current_drum_group):
                self._select_playable_mode(KEYBOARD_MODE, update_mode)
    
    def get_pad_mode(self):
        return self.component_map["Pad_Modes"].selected_mode

    def _select_playable_mode(self, mode, update_mode = True):
        if update_mode:
            self.component_map["Pad_Modes"].selected_mode = mode
        self.component_map["Step_Sequence"].set_pitch_provider(self.component_map[self._provider_list[mode]])
        self.component_map["Velocity_Levels"].set_pitch_provider(self.component_map[self._provider_list[mode]])

    def refresh_state(self):
        logger.info("Refresh state")
        super().refresh_state()
