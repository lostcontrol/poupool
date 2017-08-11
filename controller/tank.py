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

    hysteresis = 10
    levels_too_low = 10
    levels_eco = {
        "low": 40,
        "high": 80,
    }
    levels_overflow = {
        "low": 20,
        "high": 60,
    }

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__devices = devices
        self.levels = self.levels_eco
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
        self.__encoder.tank_height(int(round(height)))
        return height

    def set_mode(self, mode):
        logger.info("Tank level set to %s" % mode)
        self.levels = self.levels_eco if mode is "eco" else self.levels_overflow

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
            self.get_actor("Filtration").stop()
            raise StopRepeatException
        height = self.__get_tank_height()
        if height >= self.levels["low"] + self.hysteresis:
            self._proxy.normal()
            raise StopRepeatException
        elif height < self.levels_too_low:
            logger.warning("Tank TOO LOW, stopping: %d" % height)
            self.get_actor("Filtration").stop()
            raise StopRepeatException

    @do_repeat()
    def on_enter_normal(self):
        logger.info("Entering normal state")
        self.__encoder.tank_state("normal")
        self.__devices.get_valve("main").off()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_normal(self):
        height = self.__get_tank_height()
        if height < self.levels["low"] - self.hysteresis:
            self._proxy.low()
            raise StopRepeatException
        elif height >= self.levels["high"] + self.hysteresis:
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
        if height < self.levels["high"] - self.hysteresis:
            self._proxy.normal()
            raise StopRepeatException
