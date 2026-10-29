# ==================================================
#
# This file is part of CustomMaschineMK3.
# CustomMaschineMK3 is free software licensed under GPL-3.0.
# For more details, see "LICENSE" file.
# 
# Copyright (C) 2024-2025 chiaki
#
# ==================================================

# Detailed log of the framework's own events to CustomMaschineMK3.log (next to the script). The script's own events
# (buttons, views, modes, errors) always go to Live's Log.txt
LOGGING = True
LOG_LEVEL = "INFO"
LCD_ENABLED = True
from .Protocolo import SCREENS_PORT

# UDP port where a copy of the display text goes (the Pantallas program draws it on the screens). None turns it off.
SCREEN_BRIDGE_PORT = SCREENS_PORT
# Standby: pads, LEDs and buttons off and the screens show the project's welcome, until CHANNEL (or SAMPLING /
# MIXER / PLUGIN) is pressed; SHIFT + CHANNEL goes back to standby. True = the script starts in standby.
START_IN_STANDBY = True