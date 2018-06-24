import pykka
import time
import logging
import datetime
#from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import StopRepeatException, repeat, do_repeat
from .util import Timer

logger = logging.getLogger(__name__)


class Swim(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    states = ["stop", "timed", "continuous"]

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__devices = devices
        self.__timer = Timer("swim")
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Swim.states, initial="stop")

        self.__machine.add_transition("timed", "stop", "timed", conditions="filtration_allow_swim")
        self.__machine.add_transition("timed", "continuous", "timed",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("continuous", "stop", "continuous",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("continuous", "timed", "continuous",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("stop", "timed", "stop")
        self.__machine.add_transition("stop", "continuous", "stop")

    def timer(self, value):
        self.__timer.delay = datetime.timedelta(minutes=value)
        logger.info("Timer for swim set to: %s" % self.__timer.delay)

    def filtration_allow_swim(self):
        actor = self.get_actor("Filtration")
        is_wintering = actor.is_wintering_waiting().get() or actor.is_wintering_stir().get()
        is_opened = actor.is_overflow_normal().get() or actor.is_standby_normal().get() or actor.is_comfort().get()
        return is_opened or is_wintering

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
