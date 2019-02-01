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

logger = logging.getLogger(__name__)


class Temperature(PoupoolActor):

    READ_DELAY = 60

    def __init__(self, encoder, sensors):
        super().__init__()
        self.__encoder = encoder
        self.__sensors = sensors
        self.__temperatures = {}

    def get_temperature(self, name):
        return self.__temperatures.get(name)

    @repeat(delay=READ_DELAY)
    def do_read(self):
        for sensor in self.__sensors:
            value = sensor.value
            # In order to avoid reading the temperature again from different actors, we cache the
            # results in a map. Other actors can then get the values from here.
            self.__temperatures[sensor.name] = value
            if value is not None:
                rounded = round(value, 1)
                logger.debug("Temperature (%s) is %.1f°C" % (sensor.name, rounded))
                f = getattr(self.__encoder, sensor.name)
                f(rounded)
            else:
                logger.warning("Temperature (%s) cannot be read!!!" % sensor.name)
