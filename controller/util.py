from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class Timer(object):

    def __init__(self, name):
        self.__duration = timedelta()
        self.__name = name
        self.__last = None
        self.__last_print = datetime(2000, 1, 1)
        self.__delay = timedelta()

    @property
    def duration(self):
        return self.__duration

    @duration.setter
    def duration(self, value):
        self.__duration = value

    @property
    def remaining(self):
        return max(timedelta(), self.__delay - self.__duration)

    @property
    def delay(self):
        return self.__delay

    @delay.setter
    def delay(self, value):
        self.__delay = value
        self.reset()

    def clear(self):
        self.__last = None

    def reset(self):
        self.clear()
        self.__duration = timedelta()

    def update(self, now, factor=1):
        if self.__last is not None:
            self.__duration += factor * (now - self.__last)
            remaining = max(timedelta(), self.delay - self.__duration)
            if self.__last_print + timedelta(seconds=20) <= now:
                logger.debug("(%s) Timer: %s Remaining: %s" %
                             (self.__name, self.__duration, remaining))
                self.__last_print = now
        self.__last = now

    def elapsed(self):
        return self.__duration >= self.__delay


def round_timedelta(x):
    return timedelta(seconds=int(x.total_seconds()))


def mapping(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


def constrain(x, out_min, out_max):
    return min(max(x, out_min), out_max)
