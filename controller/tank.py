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

    STATE_REFRESH_DELAY = 10

    states = ["stop", "low", "normal", "high"]

    def __init__(self, encoder, devices):
        super(Tank, self).__init__()
        self.__encoder = encoder
        self.__devices = devices
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Tank.states, initial="stop")

        self.__machine.add_transition("low", "stop", "low")
        self.__machine.add_transition("low", "normal", "low")
        self.__machine.add_transition("normal", "stop", "normal")
        self.__machine.add_transition("normal", "low", "normal")
        self.__machine.add_transition("normal", "high", "normal")
        self.__machine.add_transition("high", "stop", "high")
        self.__machine.add_transition("high", "normal", "high")
        self.__machine.add_transition("stop", "low", "stop")
        self.__machine.add_transition("stop", "normal", "stop")
        self.__machine.add_transition("stop", "high", "stop")

    def __get_tank_height(self):
        height = self.__devices.get_sensor("tank").value
        logger.debug("Tank level: %d" % height)
        self.__encoder.tank_height(height)
        return height

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__encoder.tank_state("stop")
        self.__devices.get_valve("main").off()

    @do_repeat()
    def on_enter_low(self):
        logger.info("Entering low state")
        self.__encoder.tank_state("low")
        self.__devices.get_valve("main").on()

    @repeat(delay=STATE_REFRESH_DELAY / 2)
    def do_repeat_low(self):
        # Security feature: stop if we stay too long in this state
        if self.__machine.get_time_in_state() > datetime.timedelta(hours=6):
            logger.warning("Tank TOO LONG in low state, stopping")
            filtration = self.get_actor("Filtration")
            if filtration:
                filtration.stop()
            raise StopRepeatException
        height = self.__get_tank_height()
        if height >= 40:
            self._proxy.normal()
            raise StopRepeatException
        elif height < 10:
            logger.warning("Tank TOO LOW, stopping: %d" % height)
            filtration = self.get_actor("Filtration")
            if filtration:
                filtration.stop()
            raise StopRepeatException

    @do_repeat()
    def on_enter_normal(self):
        logger.info("Entering normal state")
        self.__encoder.tank_state("normal")
        self.__devices.get_valve("main").off()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_normal(self):
        height = self.__get_tank_height()
        if height < 25:
            self._proxy.low()
            raise StopRepeatException
        elif height >= 75:
            self._proxy.high()
            raise StopRepeatException

    @do_repeat()
    def on_enter_high(self):
        logger.info("Entering high state")
        self.__encoder.tank_state("high")
        self.__devices.get_valve("main").off()

    @repeat(delay=STATE_REFRESH_DELAY * 2)
    def do_repeat_high(self):
        height = self.__get_tank_height()
        if height < 60:
            self._proxy.normal()
            raise StopRepeatException
