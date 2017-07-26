import pykka
import transitions
#from transitions.extensions import HierarchicalGraphMachine as Machine
from transitions.extensions import HierarchicalMachine as Machine
import time
import datetime
import logging
import functools
import re

logger = logging.getLogger(__name__)


class Timer(object):

    def __init__(self, name):
        self.__duration = datetime.timedelta()
        self.__name = name
        self.__last = None
        self.__delay = 0

    @property
    def delay(self):
        return self.__delay

    @delay.setter
    def delay(self, value):
        self.__delay = value
        self.reset()

    def reset(self):
        self.__last = None
        self.__duration = datetime.timedelta()

    def update(self, now):
        if self.__last:
            self.__duration += (now - self.__last)
            remaining = max(datetime.timedelta(), self.delay - self.__duration)
            logger.debug("(%s) Timer: %s Remaining: %s" % (self.__name, self.__duration, remaining))
        self.__last = now

    def elapsed(self):
        return self.__duration >= self.__delay


class StopRepeatException(Exception):
    pass


def repeat(delay=10):
    assert delay >= 0

    def wrap(func):
        @functools.wraps(func)
        def wrapped_func(self, *args, **kwargs):
            try:
                func(self, *args, **kwargs)
            except StopRepeatException:
                pass
            else:
                if delay > 0:
                    self._proxy.do_delay(delay, func.__name__)
                else:
                    function = getattr(self._proxy, func.__name__)
                    function(*args, **kwargs)
        return wrapped_func
    return wrap


def do_repeat():
    def wrap(func):
        @functools.wraps(func)
        def wrapped_func(self, *args, **kwargs):
            try:
                func(self, *args, **kwargs)
            except StopRepeatException:
                pass
            else:
                method = re.sub("on_enter_", "do_repeat_", func.__name__)
                function = getattr(self, method)
                function()
        return wrapped_func
    return wrap


class PoupoolModel(Machine):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("before_state_change", []).extend(["do_cancel", self.__update_state_time])
        super().__init__(
            auto_transitions=False,
            ignore_invalid_triggers=True,
            *args,
            **kwargs
        )
        self.__state_time = None

    def __update_state_time(self):
        self.__state_time = datetime.datetime.now()

    def get_time_in_state(self):
        return datetime.datetime.now() - self.__state_time


class PoupoolActor(pykka.ThreadingActor):

    def __init__(self):
        super().__init__()
        self._proxy = self.actor_ref.proxy()
        self.__delay_counter = 0

    def get_actor(self, name):
        fsm = pykka.ActorRegistry.get_by_class_name(name)
        if fsm:
            return fsm[0].proxy()
        logging.critical("Actor %s not found!!!" % name)
        return None

    def do_cancel(self):
        self.__delay_counter += 1

    def do_delay(self, delay, method, *args, **kwargs):
        assert type(method) == str
        self.__delay_counter += 1
        self.do_delay_internal(self.__delay_counter, delay, method, *args, **kwargs)

    def do_delay_internal(self, counter, delay, method, *args, **kwargs):
        if counter == self.__delay_counter:
            if delay > 0:
                time.sleep(0.1)
                self._proxy.do_delay_internal(counter, delay - 0.1, method, *args, **kwargs)
            else:
                func = getattr(self._proxy, method)
                func(*args, **kwargs)
