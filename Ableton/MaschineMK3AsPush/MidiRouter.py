"""Decides what happens with every MIDI message from the Maschine: whether it reaches Ableton, and what the script
does with it (VirtualDJ mode, pad lock, standby, the modifier combinations).

It imports nothing from Live, so it runs and is tested outside Live (tests/). The script owns the side effects: the
router calls them by name through run(name, *args), in the order they happen, and reads what it needs from Live
(modifiers held, display / encoder modes) through an environment object. It also owns the routing state (the modes
and the modifiers being held), which the rest of the script reads from it.

contrato/controles.py says which program reacts to each control in each mode; tools/validar_contrato.py checks it
against this router.
"""

from time import perf_counter

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
STANDBY_WAKE_BUTTONS = ((0xB1, 34), (0xB1, 35), (0xB1, 36), (0xB1, 37))
VDJ_EXIT_BUTTONS = ((0xB1, 35), (0xB1, 36), (0xB1, 37))
# Buttons that keep controlling Ableton even in VirtualDJ mode: PLAY, STOP, TAP (messages and their LEDs).
# SHIFT (sysex from the MK3 / Plus) also gets through, so SHIFT + STOP and SHIFT + TAP (metronome) work too.
ABLETON_ALWAYS_BUTTONS = ((0xB1, 57), (0xB1, 59), (0xB1, 55))
SHIFT_SYSEX_PREFIX = (0xF0, 0x00, 0x21, 0x09)
# VOLUME / SWING / TEMPO (encoder = master / cue volume / tempo) are shared with VirtualDJ: in VirtualDJ mode Ableton still follows
# their presses (without LEDs) so the encoder mode stays the same in both programs
SHARED_ENCODER_MODE_BUTTONS = ((0xB1, 44), (0xB1, 45), (0xB1, 47))  # VOLUME, SWING, TEMPO (mutually exclusive)
# "FOLLOW" is a modifier in Ableton (FOLLOW + knob launches a clip); its LED stays off there.
# In VirtualDJ mode it belongs to VirtualDJ (its Ableton Link effect) and its LED too.
LINK_BUTTON = (0xB1, 56)
# "LOCK" pressed in VirtualDJ mode keeps the pads with VirtualDJ after going back to Ableton ("pad lock").
# Pressing "LOCK" in Ableton releases them. VirtualDJ's mapping mirrors the same logic.
PAD_LOCK_BUTTON = (0xB1, 48)
# Locked to VirtualDJ along with the pads: the A-H group buttons and the touch strip (VirtualDJ's crossfader)
GROUP_BUTTON_CCS = range(100, 108)
PAD_NOTES = range(60, 76)
KNOB_COUNT = 8
# Knob touch (CC 10-17, MIDI channel 2), with a modifier held: see the knob section of MidiRouter._accept
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

# Side effects that only keep the script in step (no sound, no view change): tools/validar_contrato.py lists them
# apart, like VirtualDJ's own variable tracking
STATE_ONLY_EFFECTS = ("_log", "_reset_encoder_mode", "_close_note_repeat_selector")


def is_vdj_only(midi_bytes):
    # Note on / off / poly pressure of the VirtualDJ-only buttons
    midi_bytes = tuple(midi_bytes)
    return (len(midi_bytes) == 3 and midi_bytes[0] & 0xF0 in (0x80, 0x90, 0xA0)
            and midi_bytes[0] & 0x0F == VDJ_ONLY_CHANNEL and midi_bytes[1] in VDJ_ONLY_NOTES)


def is_pad_section(midi_bytes, include_lock = False):
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


class MidiRouter:
    """The routing state and the rules. The environment (env) gives, read when needed:
    shift_pressed, solo_pressed, erase_pressed, mute_pressed, macro_pressed, plugin_pressed (the framework's view of
    those buttons), encoder_tempo_mode (bool), display_mode and encoder_mode (the selected mode names)."""

    def __init__(self, standby = False, clock = perf_counter):
        self.standby = standby
        self.vdj_mode = False
        self.pad_lock = False
        self.shift_down = False  # SHIFT, tracked here too: SHIFT + CHANNEL must not depend on the framework
        self.scene_down = False
        self.restart_held = False
        self.restart_used = False
        self.follow_held = False
        self.follow_used = False
        self.swallow_lock_release = False
        self.swallow_tempo_release = False
        self.erase_touch = (None, 0.0)  # (knob index, time) of the last ERASE + knob touch
        self._clock = clock

    def accept(self, midi_bytes, env, run):
        """True if the message goes on to Ableton. run(name, *args) does each side effect, in order."""
        return self._accept(tuple(midi_bytes), env, run)

    def lets_out(self, midi_event_bytes):
        """True if a message the script sends may reach the Maschine (its LEDs and display)."""
        key = tuple(midi_event_bytes[:2])
        # Standby: nothing reaches the Maschine's LEDs or display (the script blanks them itself)
        if self.standby:
            return False
        # FOLLOW's LED stays off in Ableton (the script turns it off itself) and is VirtualDJ's in VirtualDJ mode
        if key == LINK_BUTTON:
            return False
        # VirtualDJ owns LEDs and display while VirtualDJ mode is active, except Ableton's own transport buttons
        if self.vdj_mode and key not in ABLETON_ALWAYS_BUTTONS:
            return False
        if is_vdj_only(midi_event_bytes):
            return False
        # Pads locked to VirtualDJ keep VirtualDJ's colors, page button LEDs and the lit LOCK button
        if self.pad_lock and is_pad_section(midi_event_bytes, include_lock = True):
            return False
        return True

    def _set_standby(self, enabled, run):
        if enabled:
            # VirtualDJ's mapping also leaves its mode with SHIFT + CHANNEL
            self.vdj_mode = False
            self.pad_lock = False
        self.standby = enabled
        run("_on_standby_changed", enabled)

    def _set_vdj_mode(self, enabled, run):
        self.vdj_mode = enabled
        run("_on_vdj_mode_changed", enabled)

    def _accept(self, midi_bytes, env, run):
        if is_vdj_only(midi_bytes):
            return False
        is_cc = len(midi_bytes) == 3
        key = midi_bytes[:2]
        if midi_bytes[:4] == SHIFT_SYSEX_PREFIX and len(midi_bytes) > 12:
            self.shift_down = midi_bytes[-2] > 0
        elif is_cc and key == SHIFT_BUTTON:
            self.shift_down = midi_bytes[2] > 0
        elif is_cc and key == SCENE_BUTTON:
            self.scene_down = midi_bytes[2] > 0  # tracked here too; SCENE still reaches the framework (SCENE + pad)
        if is_cc and midi_bytes[0] == 0xB1 and midi_bytes[2] > 0 and midi_bytes[1] in BUTTON_NAMES:
            run("_log", f"button {BUTTON_NAMES[midi_bytes[1]]} pressed (shift = {self.shift_down}, "
                        f"standby = {self.standby}, vdj = {self.vdj_mode})")
        if is_cc and not self.vdj_mode and not self.standby:
            if key == SESSION_NAV_PUSH and self.scene_down:
                if midi_bytes[2] > 0:
                    run("_launch_cursor_scene")
                return False
            if key == PATTERN_BUTTON:
                if midi_bytes[2] > 0:
                    run("_capture_scene")
                return False
        if is_cc and not self.standby:
            # Also in VirtualDJ mode: the tempo view opened from there controls Ableton's tempo the same way
            # (VirtualDJ's mapping ignores the encoder in its encoder mode 3 and the driver draws the view)
            if key == ENCODER_TURN_BUTTON and not self.shift_down and env.encoder_tempo_mode:
                run("_turn_tempo", midi_bytes[2])
                return False
            if key == TEMPO_BUTTON:
                if midi_bytes[2] > 0 and self.shift_down:
                    # SHIFT + TEMPO: sync with VirtualDJ, in any view, leaving the view as it is; the press never
                    # reaches the encoder mode component, which would toggle the tempo view
                    self.swallow_tempo_release = True
                    run("_sync_tempo_with_virtualdj")
                    return False
                if midi_bytes[2] == 0 and self.swallow_tempo_release:
                    self.swallow_tempo_release = False
                    return False
        if is_cc and key == MACRO_BUTTON and midi_bytes[2] > 0 and self.shift_down:
            run("_restart_screens")
            return False
        if self.standby:
            # Everything is ignored, except SHIFT's state and the buttons that wake the Maschine
            if midi_bytes[:4] == SHIFT_SYSEX_PREFIX:
                return True
            if is_cc and midi_bytes[2] > 0:
                if key == VDJ_ENTER_BUTTON:
                    self._set_standby(False, run)
                    self._set_vdj_mode(True, run)
                elif key in STANDBY_WAKE_BUTTONS:
                    self._set_standby(False, run)
                    return key != STANDBY_BUTTON  # MIXER / PLUGIN also go on to select their view
            return False
        if is_cc and key == STANDBY_BUTTON and midi_bytes[2] > 0 and (self.shift_down or env.shift_pressed):
            self._set_standby(True, run)
            return False
        # "SAMPLING" never reaches Ableton, it's reserved for entering VirtualDJ mode
        if is_cc and key == VDJ_ENTER_BUTTON:
            if midi_bytes[2] > 0:
                # A view button too: VOLUME / SWING / TEMPO off
                run("_reset_encoder_mode")
                if not self.vdj_mode:
                    self._set_vdj_mode(True, run)
            return False

        # FOLLOW is a modifier only: FOLLOW + knob launches the clip of that knob's track in the cursor's scene.
        # It no longer toggles Ableton Link (Link is still on / off from Live itself)
        if is_cc and key == LINK_BUTTON and not self.vdj_mode:
            if midi_bytes[2] > 0:
                self.follow_held, self.follow_used = True, False
            else:
                self.follow_held = False
            return False

        # RESTART + SOLO (in either order): every track out of the prelisten / solo
        if (is_cc and midi_bytes[2] > 0 and not self.vdj_mode
                and ((key == SOLO_BUTTON and self.restart_held) or (key == RESTART_BUTTON and env.solo_pressed))):
            self.restart_held, self.restart_used = key == RESTART_BUTTON or self.restart_held, True
            run("_clear_prelisten")
            return False

        if is_cc and key == PAD_LOCK_BUTTON:
            if midi_bytes[2] > 0:
                if self.vdj_mode:
                    self.pad_lock = not self.pad_lock
                    run("_log", f"pad lock = {self.pad_lock}")
                    return False
                if self.pad_lock:
                    # In Ableton, LOCK only releases the pads; the press (and its release) never reach Ableton
                    self.pad_lock = False
                    run("_on_pad_lock_changed", False)
                    self.swallow_lock_release = True
                    return False
            elif self.swallow_lock_release:
                self.swallow_lock_release = False
                return False

        # RESTART is also a modifier: its loop on / off happens on release, only if no knob was touched meanwhile
        if is_cc and key == RESTART_BUTTON and not self.vdj_mode:
            if midi_bytes[2] > 0:
                self.restart_held, self.restart_used = True, False
                if self.shift_down or env.shift_pressed:
                    # SHIFT + RESTART: every volume in the mixer back to its default (not the loop toggle)
                    self.restart_used = True
                    run("_reset_all_volumes")
            else:
                if self.restart_held and not self.restart_used:
                    run("_toggle_loop")
                self.restart_held = False
            return False

        if is_cc and key in KNOB_TOUCH_CCS and midi_bytes[2] > 0 and not self.vdj_mode:
            index = KNOB_TOUCH_CCS.index(key)
            volume_view = env.display_mode in (MIXER_DISPLAY_MODE, SESSION_DISPLAY_MODE)
            if self.restart_held:
                # RESTART + knob: default value (device parameter's default, mixer volume to 0 dB...)
                self.restart_used = True
                run("_set_knob_parameter", index, True)
            elif env.erase_pressed and volume_view:
                # ERASE + double touch on a knob in the mixer / session view: to zero (volume to -inf, pan to
                # center). Double, so it can't happen by accident
                now = self._clock()
                last_index, last_time = self.erase_touch
                if last_index == index and now - last_time <= ERASE_DOUBLE_TOUCH_SECONDS:
                    run("_set_knob_parameter", index, False)
                    self.erase_touch = (None, 0.0)
                else:
                    self.erase_touch = (index, now)
            elif env.mute_pressed and volume_view:
                # MUTE + knob: stop the clip playing on that knob's track
                run("_stop_knob_track_clip", index)
            elif env.solo_pressed and volume_view:
                # SOLO + knob: that knob's track to the prelisten (solo / cue, as Live's Solo / Cue switch says)
                run("_toggle_knob_track_prelisten", index)
            elif self.follow_held and volume_view:
                # FOLLOW + knob: launch the clip of that knob's track in the scene under the cursor
                self.follow_used = True
                run("_launch_knob_track_clip", index)

        if (is_cc and not self.vdj_mode
                and env.display_mode in (SESSION_DISPLAY_MODE, MIXER_DISPLAY_MODE)
                and (key in (SESSION_NAV_TURN, SESSION_NAV_PUSH) or key in SESSION_NAV_TILTS)
                and env.encoder_mode == ENCODER_DEFAULT_MODE):
            run("_handle_session_navigation", midi_bytes)
            return False

        if (is_cc and key in (LEFT_BUTTON, RIGHT_BUTTON) and not self.vdj_mode
                and env.display_mode == MIXER_DISPLAY_MODE and not env.macro_pressed and not env.plugin_pressed):
            # In the mixer, left / right change the mixer page: volume <-> pan <-> sends (FXs)
            # Letting the press through to MaschineMixerComponent.prev_parameter_button / next_parameter_button
            return True

        if is_cc and key == NEW_SCENE_BUTTON and not self.vdj_mode:
            if midi_bytes[2] > 0:
                run("_new_scene_below_cursor")
            return False

        if is_cc and key == DELETE_CLIP_BUTTON and not self.vdj_mode:
            if midi_bytes[2] > 0:
                run("_delete_clip")
            return False

        if is_cc and (key in VIEW_BUTTONS or key in PAD_PAGE_BUTTONS) and midi_bytes[2] > 0:
            # Also when the view doesn't change (e.g. MIXER while already in the mixer); the pad pages
            # (KEYBOARD, PAD MODE, CHORDS, STEP) too, like in the VirtualDJ mapping
            run("_reset_encoder_mode")

        # ARRANGER enters the session view; the other view buttons leave it (they select their own display mode)
        if is_cc and key == SESSION_VIEW_BUTTON:
            if midi_bytes[2] > 0:
                if self.vdj_mode:
                    self._set_vdj_mode(False, run)
                run("_show_session_view")
            return False

        if is_cc and key in TOUCHSTRIP_MODE_BUTTONS and midi_bytes[2] > 0 and not self.vdj_mode:
            run("_close_note_repeat_selector")

        if self.vdj_mode:
            if is_cc and key in VDJ_EXIT_BUTTONS and midi_bytes[2] > 0:
                # Leave VirtualDJ mode and let the press through, so it selects mixer / device mode as usual
                self._set_vdj_mode(False, run)
                return True
            # PLAY / STOP (and SHIFT, for SHIFT + STOP) keep driving Ableton's transport
            if midi_bytes[:4] == SHIFT_SYSEX_PREFIX:
                return True
            return is_cc and (key in ABLETON_ALWAYS_BUTTONS or key in SHARED_ENCODER_MODE_BUTTONS)

        if self.pad_lock and is_pad_section(midi_bytes):
            return False

        return True
