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

from ableton.v3.control_surface.component_map import ComponentMap
from ableton.v3.control_surface.mode import (
    ToggleBehaviour,
    MomentaryBehaviour,
    LatchingBehaviour as LatchingBehaviourBase,
    ImmediateBehaviour
)

class LatchingBehaviour(LatchingBehaviourBase):
    def __init__(self, return_on_hold = False):
        super().__init__()
        self._return_on_hold = return_on_hold

    def release_delayed(self, component, mode):
        if self._return_on_hold:
            super().release_delayed(component, mode)

def create_mappings(surface):
    # Load settings
    sequencer_style = surface._settings.get_value("sequencer_style")
    mixer_mode = surface._settings.get_value("mixer_mode")

    mappings = {}
    mappings["Transport"] = dict(
        stop_button = "stop",
        loop_button = "restart",
        nudge_down_button = "row2_pads_with_shift_raw[2]",
        nudge_up_button = "row2_pads_with_shift_raw[3]"
    )

    mappings["View_Based_Recording"] = dict(
        overdub_button = "erase_with_shift"
    )

    # Mapping names not found in component map are recognized as mode definition
    mappings["Transport_Modes"] = dict(
        default_behaviour = MomentaryBehaviour(),
        shift_button = "shift",
        default = dict(
            component = "Transport",
            play_button = "play",
            tap_tempo_button = "tap",
            record_quantize_button = "follow",
            automation_arm_button = "auto"),
        shift = dict(
            component = "Transport",
            play_pause_button = "play",
            metronome_button = "tap",
            re_enable_automation_button = "auto")
    )

    mappings["Recording_Modes"] = dict(
        default_behaviour = MomentaryBehaviour(),
        shift_button = "shift",
        default = dict(
            component = "View_Based_Recording",
            record_button = "rec"),
        shift = dict(
            component = "Transport",
            capture_midi_button = "rec"),
    )

    mappings["Misc_Control"] = dict(
        new_audio_or_return_track_button = "file",
        new_midi_track_button = "file_with_shift",
        duplicate_track_button = "file_with_duplicate",
        delete_track_button = "file_with_erase"
    )

    mappings["Encoder_Modes"] = dict(
        default_behaviour = ToggleBehaviour(return_to_default = True),
        default = dict(
            modes = [
                dict(component = "Misc_Control",
                    select_track_encoder = "encoder",
                    exclusive_arm_button = "encoderpush",
                    arm_button = "encoderpush_with_shift"),
                # The grid moves 4 tracks sideways (a page) and 1 scene up / down
                dict(component = "Session_Navigation",
                    up_button = "encoderup",
                    down_button = "encoderdown",
                    page_left_button = "encoderleft",
                    page_right_button = "encoderright",
                )]),
        device = dict(
            modes = [
                dict(component = "Misc_Control",
                    select_track_encoder = "encoder",
                    exclusive_arm_button = "encoderpush",
                    arm_button = "encoderpush_with_shift"),
                dict(component = "Device_Navigation",
                    scroll_up_button = "encoderleft",
                    scroll_down_button = "encoderright",
                )]),
        volume = dict(
            component = "Master_Volume",
            master_volume = "encoder",
            reset_button = "encoderpush"),
        # SWING: headphones (cue) volume, like VOLUME does with the master volume
        swing = dict(
            component = "Cue_Volume",
            master_volume = "encoder",
            reset_button = "encoderpush"),
        position = dict(
            component = "Transport",
            arrangement_position_encoder = "encoder",
            loop_start_encoder = "encoder_with_shift",
            set_cue_button = "encoderpush",
            prev_cue_button = "encoderup",
            next_cue_button = "encoderdown",
            rewind_button = "encoderleft",
            fastforward_button = "encoderright"),
        tempo = dict(
            component = "Transport",
            tempo_coarse_encoder = "encoder",
            tempo_fine_encoder = "encoder_with_shift"),
        scale = dict(
            component = "Scale_System",
            select_encoder = "encoder",
            toggle_button = "encoderpush",
            up_button = "encoderup",
            down_button = "encoderdown",
            left_button = "encoderleft",
            right_button = "encoderright"),
        browser = dict(
            component = "Browser",
            select_encoder = "encoder",
            load_button = "encoderpush",
            enter_folder_button = "encoderright",
            leave_folder_button = "encoderleft",
            jump_next_button = "encoderdown",
            jump_prev_button = "encoderup"),
        settings = dict(
            component = "Settings",
            select_encoder = "encoder"),
    )

    mappings["Encoder_Mode_Control"] = dict(
        volume_button = "volume",
        swing_button = "swing",
        tempo_button = "tempo",
        shift_button = "shift",
    )
    
    mappings["TouchStrip_Modes"] = dict(
        default_behaviour = LatchingBehaviour(),
        pitch_button = "pitch",
        mod_button = "mod",
        perform_button = "perform",
        #notes_button = "notes",
        pitch = dict(
            component = "Maschine_Playable",
            pitchbend_encoder = "touchstrip",
            pitchbend_reset = "touchstripcap"
        ),
        mod = dict(
            component = "Selected_Parameter",
            modulation_encoder = "touchstrip",
            select_buttons = "track_buttons_with_mod"
        ),
        perform = dict(
            component = "Mixer",
            crossfader_control = "touchstrip"
        ),
        # notes = dict(
        #     component = "NoteRepeat",
        #     rate_selector = "touchstrip"
        # )
    )

    mappings["Pad_Modes"] = dict(
        default_behaviour = LatchingBehaviour(),
        default_button = "padmode",
        keyboard_button = None,
        drum_rack_button = None,
        simpler_button = None,
        chord_button = "chords",
        step_button = "step",
        default = dict(
            modes = [
                dict(component = "Session",
                    stop_track_clip_buttons = "row3_pads_with_mute",
                    clip_launch_buttons = "pads",
                    scene_launch_buttons = "column3_pads_with_scene",
                    select_button = "select",
                    delete_button = "erase",
                    copy_button = "duplicate"),
            ]),
        keyboard = dict(
            modes = [
                dict(component = "Maschine_Playable",
                    matrix = "pads",
                    scroll_down_button = "row0_pads_with_shift_raw[0]",
                    scroll_up_button = "row0_pads_with_shift_raw[1]",
                    scroll_page_down_button = "row0_pads_with_shift_raw[2]",
                    scroll_page_up_button = "row0_pads_with_shift_raw[3]",
                    select_button = "select",
                    delete_button = "erase"),
            ]
        ),
        drum_rack = dict(
            modes = [
                dict(component = "Drum_Group",
                    matrix = "pads",
                    mute_button = "mute",
                    solo_button = "solo",
                    scroll_down_button = "row0_pads_with_shift_raw[0]",
                    scroll_up_button = "row0_pads_with_shift_raw[1]",
                    scroll_page_down_button = "row0_pads_with_shift_raw[2]",
                    scroll_page_up_button = "row0_pads_with_shift_raw[3]",
                    select_button = "select",
                    delete_button = "erase",
                    copy_button = "duplicate",
                    clear_all_solo_button = "solo_with_erase",
                    clear_all_mute_button = "mute_with_erase"),
            ]
        ),
        simpler = dict(
            modes = [
                dict(component = "Sliced_Simpler",
                    matrix = "pads",
                    scroll_down_button = "row0_pads_with_shift_raw[0]",
                    scroll_up_button = "row0_pads_with_shift_raw[1]",
                    scroll_page_down_button = "row0_pads_with_shift_raw[2]",
                    scroll_page_up_button = "row0_pads_with_shift_raw[3]",
                    select_button = "select",
                    delete_button = "erase"),
            ]
        ),
        chord = dict(
            modes = [
                dict(component = "Velocity_Levels",
                    matrix = "pads",
                    select_button = "select"),
            ]
        ),
        step = dict(
            component = "Step_Sequence",
            step_buttons = "pads" if sequencer_style == "Push" else "original_order_pads",
            loop_copy_button = "duplicate",
            loop_delete_button = "erase",
            prev_page_button = "row0_pads_with_shift_raw[2]",
            next_page_button = "row0_pads_with_shift_raw[3]",
            select_button = "select",
        ),
        # Pads locked to VirtualDJ ("pad lock"): no component uses them
        vdj_locked = dict(component = "Pad_Lock"),
    )

    mappings["Group_Button_Modes"] = dict(
        default = dict(
            # A-H = 8 zones of 4 tracks (the grid moves 4 tracks sideways, 1 scene up / down)
            component = "Session_Zones",
            zone_buttons = "group_buttons",
        ),
        keyboard = dict(
            component = "Maschine_Playable",
            octave_select_buttons = "group_buttons",
        ),
        drum_rack = dict(
            component = "Drum_Group",
            select_buttons = "group_buttons",
        ),
        simpler = dict(
            component = "Sliced_Simpler",
            select_buttons = "upper_group_buttons",
        ),
        chord = dict(
            component = "Velocity_Levels",
            # No mapping, just placeholder
        ),
        step = dict(
            component = "Step_Sequence",
            loop_buttons = "group_buttons",
        ),
        note_repeat = dict(
            component = "Note_Repeat",
            rate_select_buttons = "group_buttons",
        ),
    )

    mappings["Display_Modes"] = dict(
        default_behaviour = LatchingBehaviour(),
        default_button = "mixer",
        device_button = "plugin",
        clip_button = "sampling",
        browser_button = "browser",
        settings_button = "setting",
        custom_button = "channel",
        default = dict(), # This is placeholder, first-defined mode will be default mode at initial state
        device = dict(
            modes = [
                dict(component = "Device",
                    parameter_controls = "knobs",
                    knob_touch_buttons = "knob_touch_buttons",
                    prev_bank_button = "left",
                    next_bank_button = "right",
                    bank_select_buttons = "track_buttons_with_macro",
                    erase_button = "erase"
                    # VARIATION deletes the locked track's clip now (MaschineMK3AsPush._delete_target_clip):
                    # no more compare A/B or copy to other here
                ),
                dict(component = "Device_Navigation",
                    select_buttons = "track_buttons",
                    on_off_buttons = "track_buttons_with_mute",
                    delete_button = "erase",
                    prev_page_button = "left_with_plugin",
                    next_page_button = "right_with_plugin",
                    select_encoder = "encoder_with_plugin",
                    view_button = "plugin",
                )
            ]),
        clip = dict(
            component = "Clip_Editor",
            #control_buttons = "track_buttons",
            mute_button = "track_buttons_raw[0]",
            loop_button = "track_buttons_raw[1]",
            crop_button = "track_buttons_raw[2]",
            launch_mode_button = "track_buttons_raw[4]",
            launch_quantize_button = "track_buttons_raw[5]",
            legato_button = "track_buttons_raw[6]",
            warp_button = "track_buttons_raw[7]",
            fine_grain_button = "macro",
            control_encoders = "knobs",
            encoder_touch_buttons = "knob_touch_buttons"
        ),
        browser = dict(
            behaviour = ToggleBehaviour(),
            component = "Browser",
            preview_toggle_button = "track_buttons_with_macro_raw[0]",
            select_folder_buttons = "track_buttons"
            # VARIATION deletes the locked track's clip now: no more hotswap here
        ),
        settings = dict(
            behaviour = ToggleBehaviour(),
            component = "Settings",
            value_encoder = "knobs_raw[0]"
        ),
        custom = dict(
            component = "Pageable_Background",
            user_buttons = "track_buttons",
            user_knobs = "knobs",
            learn_button = "macro",
            knob_touch_buttons = "knob_touch_buttons",
            scroll_up_button = "left",
            scroll_down_button = "right"
        ),
        # ARRANGER: clip grid on the screens, the 8 knobs control the volume of its 8 tracks, or with the
        # right arrow the selected device's parameters like PLUGIN (left arrow: volumes again).
        # (selected by MaschineMK3AsPush._set_session_view; the other view buttons leave it)
        # Device stays enabled, without controls, so it keeps following the selected device and bank
        session = dict(
            modes = [
                dict(component = "Session_Volume",
                    volume_controls = "knobs",
                    # Mapped so Live forwards the knob touches: the screens draw a pop-up for each touched knob
                    knob_touch_buttons = "knob_touch_buttons",
                    volume_page_button = "left",
                    fx_page_button = "right"),
                dict(component = "Device"),
            ])
    )

    if mixer_mode == "4Track":
        mappings["Display_Modes"]["default"] = dict(
            component = "Mixer",
            shift_button = "shift",
            pan_or_send_controls = "left_half_knobs",
            prev_control_button = "left",
            next_control_button = "right",
            volume_controls = "right_half_knobs",
            arm_buttons = "left_half_track_buttons",
            mute_buttons = "left_half_track_buttons_with_mute",
            solo_buttons = "left_half_track_buttons_with_solo",
            track_select_buttons = "right_half_track_buttons",
            knob_touch_buttons = "knob_touch_buttons"
            # No erase_button: ERASE + knob sends it to zero and RESTART + knob to its default
            # (MaschineMK3AsPush._accept_midi); ERASE + double touch would fight with that
        )
        mappings["Mixer"] = dict(
            crossfade_cycle_buttons = "upper_group_buttons_with_perform"
        )
    else:
        mappings["Display_Modes"]["default"] = dict(
            component = "Mixer",
            shift_button = "shift",
            parameter_controls = "knobs",
            parameter_select_buttons = "track_buttons_with_macro",
            prev_parameter_button = "left",
            next_parameter_button = "right",
            scroll_up_button = "left_with_macro",
            scroll_down_button = "right_with_macro",
            arm_buttons = "track_buttons_with_select",
            mute_buttons = "track_buttons_with_mute",
            solo_buttons = "track_buttons_with_solo",
            track_select_buttons = "track_buttons",
            knob_touch_buttons = "knob_touch_buttons"
            # No erase_button: ERASE + knob sends it to zero and RESTART + knob to its default
            # (MaschineMK3AsPush._accept_midi); ERASE + double touch would fight with that
        )
        mappings["Mixer"] = dict(
            crossfade_cycle_buttons = "group_buttons_with_perform"
        )

    mappings["Session"] = dict(stop_all_clips_button = "stop_with_shift")

    # ARRANGER no longer toggles Session / Arrangement: it shows the clip grid on the Maschine's screens
    # (MaschineMK3AsPush._set_session_view)
    mappings["View_Toggle"] = dict(
        browser_view_toggle_button = "browser_with_shift",
    )

    mappings["Undo_Redo"] = dict(
        undo_button = "row3_pads_with_shift_raw[0]",
        redo_button = "row3_pads_with_shift_raw[1]"
    )

    mappings["Clip_Actions"] = dict(
        double_button = "duplicate_with_shift",
        quantize_button = "row2_pads_with_shift_raw[0]",
        half_quantize_button = "row2_pads_with_shift_raw[1]"
    )

    mappings["Accent"] = dict(
        accent_button = "fixedvel"
    )

    mappings["Selected_Parameter"] = dict(
        reset_value_button = "mod_with_erase",
        select_modifier = "mod"
    )

    mappings["Target_Track"] = dict(
        lock_button = "lock"
    )

    mappings["Device"] = dict(
        device_lock_button = "lock_with_plugin"
    )

    mappings["Note_Repeat"] = dict(
        repeat_button = "noterep",
        lock_button = "lock_with_noterep",
    )

    mappings["Group_Button_Mode_Control"] = dict(
        notes_button = "notes"
    )

    mappings["Maschine_Playable"] = dict(
        pedal_tip_encoder = "pedaltip",
        pedal_ring_encoder = "pedalring",
    )

    return mappings
