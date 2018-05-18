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


class Arduino(PoupoolActor):

    STATE_REFRESH_DELAY = 60

    states = ["stop", "run"]

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__arduino = devices.get_valve("arduino")
        self.__water_counter = 0
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Arduino.states, initial="stop")

        self.__machine.add_transition("run", "stop", "run")
        self.__machine.add_transition("stop", "run", "stop")

    def cover_open(self):
        self.__arduino.cover_open()

    def cover_close(self):
        self.__arduino.cover_close()

    def cover_stop(self):
        self.__arduino.cover_stop()

    def cover_position(self):
        return self.__arduino.cover_position

    def water_counter(self):
        return self.__water_counter

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.cover_stop()

    @do_repeat()
    def on_enter_run(self):
        logger.info("Entering run state")

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_run(self):
        # Water counter
        self.__water_counter = self.__arduino.water_counter
        self.__encoder.water_counter(self.__water_counter)
