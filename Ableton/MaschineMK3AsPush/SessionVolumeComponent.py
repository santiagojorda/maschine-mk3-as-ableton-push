# ==================================================
#
# This file is part of Maschine MK3 as Push, based on CustomMaschineMK3 by chiaki.
# Maschine MK3 as Push is free software licensed under GPL-3.0.
# For more details, see "LICENSE" file.
#
# ==================================================

from ableton.v3.control_surface.component import Component
from ableton.v3.control_surface.controls import ButtonControl, MappedControl, control_list
from ableton.v3.base import depends
from ableton.v3.live import liveobj_valid

from .Logger import logger

# Same block size as the clip grid on the screens (MaschineMK3AsPush.SESSION_GRID_TRACKS)
BLOCK_TRACKS = 8
VOLUME_PAGE = "volume"
FX_PAGE = "fx"

class SessionVolumeComponent(Component):
    """Session view (ARRANGER): the 8 knobs control the volume of the 8 tracks shown on the screens,
    or (FX page, right arrow) the parameters of the target track's selected device, like the PLUGIN view.

    The screens show a fixed block of 8 tracks (1-8, 9-16...) that contains the session ring, so the
    volume knobs follow that block too. refresh() is called often by the main script; it only remaps the
    knobs when what they control changes, because remapping rebuilds Live's MIDI map.
    """

    volume_controls = control_list(MappedControl)
    knob_touch_buttons = control_list(ButtonControl, color = None)  # no action: only so the touches reach the script
    volume_page_button = ButtonControl(color = "DefaultButton.Off", on_color = "DefaultButton.On")
    fx_page_button = ButtonControl(color = "DefaultButton.Off", on_color = "DefaultButton.On")

    @depends(session_ring = None)
    def __init__(self, name = "Session_Volume", session_ring = None, *a, **k):
        super().__init__(name = name, *a, **k)
        self._session_ring = session_ring
        self._mapped = None
        self.page = VOLUME_PAGE
        self._device_component = None
        self.block_start = None  # first track of the grid on the screens (set by the main script)

    def set_volume_controls(self, controls):
        self.volume_controls.set_control_element(controls)
        self._mapped = None
        self.refresh()

    def set_device_component(self, device_component):
        # The Device component (enabled in the session mode too) keeps track of the selected device and bank
        self._device_component = device_component

    @volume_page_button.pressed
    def _on_volume_page_button_pressed(self, button):
        self._set_page(VOLUME_PAGE)

    @fx_page_button.pressed
    def _on_fx_page_button_pressed(self, button):
        self._set_page(FX_PAGE)

    def _set_page(self, page):
        if page != self.page:
            self.page = page
            self._mapped = None
            logger.info(f"Session knobs: {page}")
        self.refresh()

    def _update_page_leds(self):
        self.volume_page_button.is_on = self.page == VOLUME_PAGE
        self.fx_page_button.is_on = self.page == FX_PAGE

    def _block_volumes(self):
        tracks_to_use = getattr(self._session_ring, "tracks_to_use", None)
        tracks = list(tracks_to_use()) if callable(tracks_to_use) else list(self.song.visible_tracks)
        start = self.block_start if self.block_start is not None else self._session_ring.track_offset
        block = tracks[start:start + BLOCK_TRACKS]
        return tuple(track.mixer_device.volume if liveobj_valid(track) else None for track in block)

    def _device_parameters(self):
        component = self._device_component
        if component is None:
            return ()
        parameters = []
        for info in getattr(component, "parameters", None) or ():
            parameter = getattr(info, "parameter", info)
            parameters.append(parameter if liveobj_valid(parameter) else None)
        return tuple(parameters)

    def refresh(self):
        if not self.is_enabled() or self._session_ring is None:
            return
        self._update_page_leds()
        targets = self._device_parameters() if self.page == FX_PAGE else self._block_volumes()
        if targets == self._mapped:
            return
        self._mapped = targets
        for index, control in enumerate(self.volume_controls):
            control.mapped_parameter = targets[index] if index < len(targets) else None

    def update(self):
        super().update()
        self._mapped = None
        self.refresh()
