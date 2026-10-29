# ==================================================
#
# This file is part of Maschine MK3 as Push, based on CustomMaschineMK3 by chiaki.
# Maschine MK3 as Push is free software licensed under GPL-3.0.
# For more details, see "LICENSE" file.
#
# ==================================================

from ableton.v3.control_surface.component import Component
from ableton.v3.control_surface.controls import ButtonControl, control_list
from ableton.v3.base import depends

ZONE_COUNT = 8  # A-H


class SessionZonesComponent(Component):
    """The group buttons A-H as 8 zones of tracks (A = the first 4 tracks, B = the next 4...).

    Pressing one moves the session ring there, keeping its scene: the grid only moves by 4 tracks sideways and by 1
    scene up / down. It replaces Live's session overview, whose second row jumped a whole page of scenes. The lit
    button is the zone on the pads; nothing else lights.
    """

    zone_buttons = control_list(ButtonControl, color = "Zooming.Empty", on_color = "Zooming.Selected")

    @depends(session_ring = None)
    def __init__(self, name = "Session_Zones", session_ring = None, *a, **k):
        super().__init__(name = name, *a, **k)
        self._session_ring = session_ring
        self.zone_buttons.control_count = ZONE_COUNT

    @zone_buttons.pressed
    def _on_zone_pressed(self, button):
        ring = self._session_ring
        tracks_to_use = getattr(ring, "tracks_to_use", None)
        tracks = tracks_to_use() if callable(tracks_to_use) else self.song.visible_tracks
        offset = button.index * ring.num_tracks
        if offset < len(list(tracks)):
            ring.set_offsets(offset, ring.scene_offset)
        self.refresh()

    def refresh(self):
        if self._session_ring is None:
            return
        selected = self._session_ring.track_offset // self._session_ring.num_tracks
        for index, button in enumerate(self.zone_buttons):
            button.is_on = index == selected

    def update(self):
        super().update()
        self.refresh()
