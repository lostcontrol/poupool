import pykka
import time
import logging
#from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel

logger = logging.getLogger("tank")

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
    
    def on_enter_low(self):
        logger.info("Entering low state")
        self.__devices.get_valve("main").on()
        self.do_state_low()

    def do_state_low(self):
        height = self.__devices.get_sensor("tank").value
        if height >= 25:
            self._proxy.normal()
        elif height < 5:
            logger.warning("Tank TOO LOW, stopping: %d" % height)
            filtration = self.get_fsm("Filtration")
            if filtration:
                filtration.stop()
        else:
            self._proxy.do_delay(Tank.STATE_REFRESH_DELAY, "do_state_low")

    def on_enter_normal(self):
        logger.info("Entering normal state")
        self.__devices.get_valve("main").off()
        self.do_state_normal()

    def do_state_normal(self):
        height = self.__devices.get_sensor("tank").value
        logger.debug("Tank level: %d" % height)
        if height < 10:
            self._proxy.low()
        else:
            self._proxy.do_delay(Tank.STATE_REFRESH_DELAY, "do_state_normal")

