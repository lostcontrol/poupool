import datetime
import logging

logger = logging.getLogger(__name__)


class Duration(object):

    def __init__(self, name):
        self.__duration = datetime.timedelta()
        self.__name = name
        self.__start = None
        self.__last = None
        self.__hour = 0
        self.__set_start()
        self.daily = datetime.timedelta()

    def __set_start(self):
        tm = datetime.datetime.now()
        self.__start = tm.replace(hour=self.__hour, minute=0, second=0, microsecond=0)
        logger.debug("(%s) Duration reset: %s" % (self.__name, self.__start))

    @property
    def hour(self):
        return self.__hour

    @hour.setter
    def hour(self, value):
        self.__hour = value
        self.__set_start()

    def clear(self):
        self.__last = None

    def update(self, now, factor=1.0):
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
        self.__set_start()
        logger.info("(%s) Reset. Duration done: %s" % (self.__name, self.__duration))
        self.__duration = datetime.timedelta()

    def elapsed(self):
        return self.__duration >= self.daily


def mapping(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


def constrain(x, out_min, out_max):
    return min(max(x, out_min), out_max)
