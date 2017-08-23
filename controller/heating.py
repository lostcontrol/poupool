import pykka
import time
import logging
import datetime
#from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import StopRepeatException, repeat, do_repeat, Timer

logger = logging.getLogger(__name__)


class Heating(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    states = ["stop", "waiting", "heating"]

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__devices = devices
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Heating.states, initial="stop")

        self.__machine.add_transition("heat", "stop", "waiting")
        self.__machine.add_transition("heat", "waiting", "heating")
        self.__machine.add_transition("stop", ["waiting", "heating"], "stop")

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__encoder.heating_state("stop")
        self.__devices.get_valve("heating").off()

    def on_enter_waiting(self):
        logger.info("Entering waiting state")
        self.__encoder.heating_state("waiting")
        self._proxy.do_delay(10, "heat")

    def on_enter_heating(self):
        logger.info("Entering heating state")
        self.__encoder.heating_state("heating")
        self.__devices.get_valve("heating").on()
