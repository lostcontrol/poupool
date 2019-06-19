# Poupool - swimming pool control software
# Copyright (C) 2019 Cyril Jaquier
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import logging
from .actor import PoupoolActor
from .actor import repeat
from serial.serialutil import SerialException

logger = logging.getLogger(__name__)


class Lcd(PoupoolActor):

    UPDATE_DELAY = 2

    def __init__(self, lcdbackpack):
        super().__init__()
        self.__cache = {}
        self.__lcdbackpack = lcdbackpack

    def on_stop(self):
        if self.__lcdbackpack:
            self.__lcdbackpack.clear()
            self.__lcdbackpack.set_brightness(16)
            self.__lcdbackpack.set_cursor_home()
            self.__lcdbackpack.write(" " * 20)
            self.__lcdbackpack.write("       POUPOOL      ")
            self.__lcdbackpack.write("     NOT RUNNING")
            self.__lcdbackpack.disconnect()
        super().on_stop()

    def update(self, key, value):
        self.__cache[key] = value

    def do_start(self):
        try:
            self.__lcdbackpack.connect()
            self.__lcdbackpack.set_lcd_size(20, 4)
            # Not supported in the version from pip
            # self.__lcdbackpack.set_splash_screen("Poupool", 20 * 4)
            self.__lcdbackpack.clear()
            self.__lcdbackpack.set_brightness(255)
            self.__lcdbackpack.display_on()
            # Go to our daily job
            self._proxy.do_update.defer()
        except SerialException:
            logger.exception("Unable to open LCD, ignoring the device")
            self.__lcdbackpack = None

    @repeat(delay=UPDATE_DELAY)
    def do_update(self):
        self.__lcdbackpack.set_cursor_home()
        self.__lcdbackpack.write(self.get_string())

    def get_string(self):
        state = self.__cache.get("filtration_state", "--")
        s = "Mode {:>15}\n".format(state.upper())[:20]
        pool = float(self.__cache.get("temperature_pool", 0))
        air = float(self.__cache.get("temperature_air", 0))
        s += "Water {:>4.1f} Air {:>5.1f}".format(pool, air)[:20]
        try:
            ph = float(self.__cache.get("disinfection_ph_value", None))
            orp = int(self.__cache.get("disinfection_orp_value", None))
            s += "pH     {:>3.1f} ORP {:>5d}".format(ph, orp)[:20]
        except (TypeError, ValueError):
            s += "pH     -.- ORP   ---"
        next_event = self.__cache.get("filtration_next", "00:00:00")
        s += "Next event  {:>8}\n".format(next_event)[:20]
        return s

    def get_printable_string(self):
        # The display is a 4x20 LCD.
        message = self.get_string()
        return "\n".join(message[20 * i: 20 * i + 20] for i in range(4))
