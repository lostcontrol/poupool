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
import statistics
import collections
from .actor import PoupoolActor
from .actor import repeat

logger = logging.getLogger(__name__)


class MovingAverage:

    def __init__(self, maxlen=6):
        self.__data = collections.deque(maxlen=maxlen)

    def clear(self):
        self.__data.clear()

    def push(self, value):
        self.__data.append(value)

    def mean(self):
        return statistics.mean(self.__data) if self.__data else None


class TemperatureReader(PoupoolActor):

    READ_DELAY = 10

    def __init__(self, sensors):
        super().__init__()
        self.__sensors = sensors
        self.__temperatures = {}

    def get_temperature(self, name):
        return self.__temperatures.setdefault(name, MovingAverage()).mean()

    def get_all_temperatures(self):
        return {k: v.mean() for k, v in self.__temperatures.items()}

    @repeat(delay=READ_DELAY)
    def do_read(self):
        for sensor in self.__sensors:
            value = sensor.value
            # In order to avoid reading the temperature again from different actors, we cache the
            # results in a map. Other actors can then get the values from here.
            if value is not None:
                self.__temperatures.setdefault(sensor.name, MovingAverage()).push(value)


class TemperatureWriter(PoupoolActor):

    READ_DELAY = 60

    def __init__(self, encoder, reader):
        super().__init__()
        self.__encoder = encoder
        self.__reader = reader

    @repeat(delay=READ_DELAY)
    def do_write(self):
        for name, value in self.__reader.get_all_temperatures().get().items():
            if value is not None:
                rounded = round(value, 1)
                logger.debug("Temperature (%s) is %.1f°C" % (name, rounded))
                f = getattr(self.__encoder, name)
                f(rounded)
            else:
                logger.warning("Temperature (%s) cannot be read!!!" % name)
