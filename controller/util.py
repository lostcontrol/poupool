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
from collections.abc import Callable
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Duration:
    def __init__(self, name: str) -> None:
        self.__name: str = name
        self.__total_duration: timedelta = timedelta()
        self.__start: datetime = datetime.now()
        self.__callback: Callable[[timedelta], None] | None = None

    def set_callback(self, callback: Callable[[timedelta], None]) -> None:
        self.__callback = callback

    def init(self, value: timedelta) -> None:
        assert isinstance(value, timedelta)
        self.__total_duration = value

    @property
    def duration(self) -> timedelta:
        return self.__total_duration

    def start(self, value: datetime | None = None) -> None:
        value = value or datetime.now()
        assert isinstance(value, datetime)
        self.__start = value

    def stop(self, value: datetime | None = None) -> None:
        value = value or datetime.now()
        assert isinstance(value, datetime)
        diff = value - self.__start
        assert diff > timedelta()
        self.__total_duration += diff
        if self.__callback:
            self.__callback(self.__total_duration)


class Timer:
    def __init__(self, name: str) -> None:
        self.__duration: timedelta = timedelta()
        self.__name: str = name
        self.__last: datetime | None = None
        self.__last_print: datetime = datetime(2000, 1, 1)
        self.__delay: timedelta = timedelta()

    @property
    def duration(self) -> timedelta:
        return self.__duration

    @duration.setter
    def duration(self, value: timedelta) -> None:
        self.__duration = value

    @property
    def remaining(self) -> timedelta:
        return max(timedelta(), self.__delay - self.__duration)

    @property
    def delay(self) -> timedelta:
        return self.__delay

    @delay.setter
    def delay(self, value: timedelta) -> None:
        self.__delay = value
        self.reset()

    def clear(self) -> None:
        self.__last = None

    def reset(self) -> None:
        self.clear()
        self.__duration = timedelta()

    def update(self, now: datetime, factor: float = 1) -> None:
        if self.__last is not None:
            self.__duration += factor * (now - self.__last)
            remaining = max(timedelta(), self.delay - self.__duration)
            if self.__last_print + timedelta(seconds=20) <= now:
                logger.debug(f"({self.__name}) Timer: {self.__duration} Remaining: {remaining}")
                self.__last_print = now
        self.__last = now

    def elapsed(self) -> bool:
        return self.__duration >= self.__delay


def round_timedelta(x: timedelta) -> timedelta:
    return timedelta(seconds=round(x.total_seconds()))


def mapping(x: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


def constrain(x: float, out_min: float, out_max: float) -> float:
    return min(max(x, out_min), out_max)
