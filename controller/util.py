import datetime
import logging

logger = logging.getLogger(__name__)


class Duration(object):

    def __init__(self, name):
        self.__duration = datetime.timedelta()
        self.__name = name
        self.__start = None
        self.__last = None
        self.daily = datetime.timedelta()
        self.hour = 0

    def clear(self):
        self.__last = None

    def update(self, now, factor=1.0):
        if not self.__start:
            self.__start = now
        if now - self.__start > datetime.timedelta(days=1):
            # reset
            self.__reset()
        elif self.__last:
            self.__duration += factor * (now - self.__last)
            remaining = max(datetime.timedelta(), self.daily - self.__duration)
            logger.debug("(%s) Duration since last reset: %s Remaining: %s" %
                         (self.__name, self.__duration, remaining))
        if factor != 0:
            self.__last = now

    def __reset(self):
        tm = datetime.datetime.now()
        self.__start = tm.replace(hour=self.hour, minute=0, second=0, microsecond=0)
        logger.info("(%s) Duration reset: %s Duration done: %s" %
                    (self.__name, self.__start, self.__duration))
        self.__duration = datetime.timedelta()

    def elapsed(self):
        return self.__duration >= self.daily


def mapping(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


def constrain(x, out_min, out_max):
    return min(max(x, out_min), out_max)
