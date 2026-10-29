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

import logging
from pathlib import Path
from . import Config

from datetime import datetime, timedelta, timezone

class ISOTimeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt = None):
        time = datetime.fromtimestamp(record.created)
        time_string = time.isoformat(timespec = "microseconds")

        return time_string

logger = logging.getLogger("MaschineMK3AsPush")
if Config.LOGGING == True and len(logger.handlers) == 0:
    file_name = Path(__file__).absolute().parent.joinpath("MaschineMK3AsPush.log")
    handler = logging.FileHandler(str(file_name))
    
    formatter = ISOTimeFormatter("%(asctime)s\t%(levelname)s\t%(message)s") # logging.Formatterの代わりに自作のクラスを使う

    handler.setFormatter(formatter)

    level_table = {
        "CRITICAL": logging.CRITICAL,
        "FATAL": logging.FATAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "WARN": logging.WARN,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }

    logger.setLevel(level_table.get(Config.LOG_LEVEL, logging.INFO))
    logger.addHandler(handler)

else:
    # Set to max level for eliminating log output
    logger.setLevel(logging.CRITICAL)
