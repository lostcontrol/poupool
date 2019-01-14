import pykka
import time
import logging
from datetime import datetime, timedelta
#from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import StopRepeatException, repeat, do_repeat
from .util import Timer

logger = logging.getLogger(__name__)


class Swim(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    states = ["halt",
              "timed",
              "continuous",
              {"name": "wintering", "initial": "waiting", "children": [
                  "stir",
                  "waiting"]}]

    def __init__(self, temperature, encoder, devices):
        super().__init__()
        self.__temperature = temperature
        self.__encoder = encoder
        self.__devices = devices
        self.__timer = Timer("swim")
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Swim.states, initial="halt")

        self.__machine.add_transition("timed", "halt", "timed", conditions="filtration_allow_swim")
        self.__machine.add_transition("wintering", "halt", "wintering",
                                      conditions="filtration_is_wintering")
        self.__machine.add_transition("wintering_stir", "wintering_waiting", "wintering_stir")
        self.__machine.add_transition("wintering_waiting", "wintering_stir", "wintering_waiting")
        self.__machine.add_transition("timed", "continuous", "timed",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("continuous", "halt", "continuous",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("continuous", "timed", "continuous",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("halt", ["timed", "continuous", "wintering"], "halt")

    def timer(self, value):
        self.__timer.delay = timedelta(minutes=value)
        logger.info("Timer for swim set to: %s" % self.__timer.delay)

    def filtration_allow_swim(self):
        actor = self.get_actor("Filtration")
        is_opened = actor.is_overflow_normal().get() or actor.is_standby_normal().get() or actor.is_comfort().get()
        return is_opened or self.filtration_is_wintering()

    def filtration_is_wintering(self):
        actor = self.get_actor("Filtration")
        return actor.is_wintering_waiting().get() or actor.is_wintering_stir().get()

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.__encoder.swim_state("halt")
        self.__devices.get_pump("swim").off()

    @do_repeat()
    def on_enter_timed(self):
        logger.info("Entering timed state")
        self.__encoder.swim_state("timed")
        self.__timer.reset()
        self.__devices.get_pump("swim").on()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_timed(self):
        self.__timer.update(datetime.now())
        if self.__timer.elapsed():
            self._proxy.halt()
            raise StopRepeatException

    def on_enter_continuous(self):
        logger.info("Entering continuous state")
        self.__encoder.swim_state("continuous")
        self.__devices.get_pump("swim").on()

    @do_repeat()
    def on_enter_wintering_waiting(self):
        logger.info("Entering wintering waiting state")
        self.__encoder.swim_state("wintering_waiting")
        self.__devices.get_pump("swim").off()

    @repeat(delay=2 * 60)
    def do_repeat_wintering_waiting(self):
        if self.__machine.get_time_in_state() > timedelta(hours=3):
            temperature = self.__temperature.get_temperature("temperature_ncc").get()
            if temperature <= 0:
                self._proxy.wintering_stir()
                raise StopRepeatException

    def on_enter_wintering_stir(self):
        logger.info("Entering wintering stir state")
        self.__encoder.swim_state("wintering_stir")
        self.__devices.get_pump("swim").on()
        self._proxy.do_delay(1 * 60, "wintering_waiting")
