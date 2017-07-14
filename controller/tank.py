import pykka
import time
import logging
import datetime
#from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import StopRepeatException, repeat, do_repeat

logger = logging.getLogger(__name__)


class Tank(PoupoolActor):

    STATE_REFRESH_DELAY = 5

    states = ["stop", "low", "normal"]

    def __init__(self, devices):
        super(Tank, self).__init__()
        self.__devices = devices
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Tank.states, initial="stop")

        self.__machine.add_transition("low", "*", "low")
        self.__machine.add_transition("normal", "*", "normal")
        self.__machine.add_transition("stop", "*", "stop")

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__devices.get_valve("main").off()

    @do_repeat()
    def on_enter_low(self):
        logger.info("Entering low state")
        self.__devices.get_valve("main").on()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_low(self):
        # Security feature: stop if we stay too long in this state
        if self.__machine.get_time_in_state() > datetime.timedelta(hours=1):
            logger.warning("Tank TOO LONG in low state, stopping")
            filtration = self.get_actor("Filtration")
            if filtration:
                filtration.stop()
            raise StopRepeatException
        height = self.__devices.get_sensor("tank").value
        if height >= 25:
            self._proxy.normal()
            raise StopRepeatException
        elif height < 5:
            logger.warning("Tank TOO LOW, stopping: %d" % height)
            filtration = self.get_actor("Filtration")
            if filtration:
                filtration.stop()
            raise StopRepeatException

    @do_repeat()
    def on_enter_normal(self):
        logger.info("Entering normal state")
        self.__devices.get_valve("main").off()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_normal(self):
        height = self.__devices.get_sensor("tank").value
        logger.debug("Tank level: %d" % height)
        if height < 10:
            self._proxy.low()
            raise StopRepeatException
