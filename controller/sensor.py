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
from datetime import timedelta

logger = logging.getLogger(__name__)


class MovingAverage:

    def __init__(self, maxlen):
        self.__data = collections.deque(maxlen=maxlen)

    def clear(self):
        self.__data.clear()

    def push(self, value):
        self.__data.append(value)

    def mean(self):
        return statistics.mean(self.__data) if self.__data else None


class BaseReader(PoupoolActor):

    def __init__(self, sensors, maxlen=10):
        super().__init__()
        self.__sensors = sensors
        self.__values = {}
        for sensor in self.__sensors:
            self.__values[sensor.name] = MovingAverage(maxlen=maxlen)

    @property
    def values(self):
        return self.__values

    def do_read(self):
        for sensor in self.__sensors:
            value = sensor.value
            if value is not None:
                self.__values[sensor.name].push(value)


class DisinfectionReader(BaseReader):

    DELAY_SECONDS = 120
    DURATION = timedelta(hours=4)

    def __init__(self, sensors):
        samples = int(self.DURATION.total_seconds() // self.DELAY_SECONDS)
        super().__init__(sensors, samples)

    def get_ph(self):
        return self.values["ph"].mean()

    def get_orp(self):
        return self.values["orp"].mean()

    def do_read(self):
        super().do_read()
        self.do_delay(self.DELAY_SECONDS, self.do_read.__name__)


class DisinfectionWriter(PoupoolActor):

    DELAY_SECONDS = 60

    def __init__(self, encoder, reader):
        super().__init__()
        self.__encoder = encoder
        self.__reader = reader

    def do_write(self):
        orp = self.__reader.get_orp().get()
        if orp:
            self.__encoder.disinfection_orp_value("%d" % orp)
        ph = self.__reader.get_ph().get()
        if ph:
            self.__encoder.disinfection_ph_value("%.2f" % ph)
        self.do_delay(self.DELAY_SECONDS, self.do_write.__name__)


class TemperatureReader(BaseReader):

    DELAY_SECONDS = 60
    DURATION = timedelta(minutes=30)

    def __init__(self, sensors):
        samples = int(self.DURATION.total_seconds() // self.DELAY_SECONDS)
        super().__init__(sensors, maxlen=samples)

    def get_temperature(self, name):
        return self.values[name].mean()

    def get_all_temperatures(self):
        return {k: v.mean() for k, v in self.values.items()}

    def do_read(self):
        super().do_read()
        self.do_delay(self.DELAY_SECONDS, self.do_read.__name__)


class TemperatureWriter(PoupoolActor):

    DELAY_SECONDS = 60

    def __init__(self, encoder, reader):
        super().__init__()
        self.__encoder = encoder
        self.__reader = reader

    def do_write(self):
        for name, value in self.__reader.get_all_temperatures().get().items():
            if value is not None:
                rounded = round(value, 1)
                logger.debug("Temperature (%s) is %.1f°C" % (name, rounded))
                f = getattr(self.__encoder, name)
                f(rounded)
            else:
                logger.warning("Temperature (%s) cannot be read!!!" % name)
        self.do_delay(self.DELAY_SECONDS, self.do_write.__name__)
