import pykka
import time
import logging
import datetime
#from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import StopRepeatException, repeat, do_repeat

logger = logging.getLogger(__name__)

class Timer(object):

    def __init__(self, name):
        self.__duration = datetime.timedelta()
        self.__name = name
        self.__last = None
        self.delay = 0

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
        return self.__duration >= self.delay


class Swim(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    states = ["stop", "timed", "continuous"]

    def __init__(self, encoder, devices):
        super(Swim, self).__init__()
        self.__encoder = encoder
        self.__devices = devices
        self.__timer = Timer("swim")
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Swim.states, initial="stop")

        self.__machine.add_transition("timed", "stop", "timed", conditions="filtration_is_overflow")
        self.__machine.add_transition("timed", "continuous", "timed", conditions="filtration_is_overflow")
        self.__machine.add_transition("continuous", "stop", "continuous", conditions="filtration_is_overflow")
        self.__machine.add_transition("continuous", "timed", "continuous", conditions="filtration_is_overflow")
        self.__machine.add_transition("stop", "timed", "stop")
        self.__machine.add_transition("stop", "continuous", "stop")

    def timer(self, value):
        self.__timer.delay = datetime.timedelta(minutes=value)
        logger.info("Timer for swim set to: %s" % self.__timer.delay)

    def filtration_is_overflow(self):
        filtration = self.get_actor("Filtration")
        if filtration:
            return filtration.is_overflow().get()
        return False

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__encoder.swim_state("stop")
        self.__devices.get_pump("swim").off()

    @do_repeat()
    def on_enter_timed(self):
        logger.info("Entering timed state")
        self.__encoder.swim_state("timed")
        self.__timer.reset()
        self.__devices.get_pump("swim").on()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_timed(self):
        self.__timer.update(datetime.datetime.now())
        if self.__timer.elapsed():
            self._proxy.stop()
            raise StopRepeatException

    def on_enter_continuous(self):
        logger.info("Entering continuous state")
        self.__encoder.swim_state("continuous")
        self.__devices.get_pump("swim").on()
