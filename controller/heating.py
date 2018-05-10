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


class Heater(PoupoolActor):

    STATE_REFRESH_DELAY = 10
    HYSTERESIS_DOWN = 0.5
    HYSTERESIS_UP = 2.0

    states = ["stop", "waiting", "heating"]

    def __init__(self, temperature, heater):
        super().__init__()
        self.__temperature = temperature
        self.__heater = heater
        self.__setpoint = 5.0
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Heating.states, initial="stop")

        self.__machine.add_transition(
            "wait", ["stop", "heating"], "waiting", conditions="has_heater")
        self.__machine.add_transition("heat", "waiting", "heating")
        self.__machine.add_transition("stop", ["waiting", "heating"], "stop")

    def has_heater(self):
        return self.__heater is not None

    def setpoint(self, value):
        self.__setpoint = value
        logger.info("Setpoint set to %.1f" % self.__setpoint)

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__heater.off()

    @do_repeat()
    def on_enter_waiting(self):
        logger.info("Entering waiting state")

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_waiting(self):
        temp = self.__temperature.value
        if temp < self.__setpoint - Heater.HYSTERESIS_DOWN:
            self._proxy.heat()
            raise StopRepeatException

    @do_repeat()
    def on_enter_heating(self):
        logger.info("Entering heating state")
        self.__heater.on()

    def on_exit_heating(self):
        self.__heater.off()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_heating(self):
        temp = self.__temperature.value
        if temp > self.__setpoint + Heater.HYSTERESIS_UP:
            self._proxy.wait()
            raise StopRepeatException


class Heating(PoupoolActor):

    STATE_REFRESH_DELAY = 10
    HYSTERESIS_DOWN = 0.5
    HYSTERESIS_UP = 0.5
    RECOVER_PERIOD = 20  # * 60

    states = ["stop", "waiting", "heating", "recovering"]

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__devices = devices
        self.__next_start = datetime.now()
        self.__setpoint = 26.0
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Heating.states, initial="stop")

        self.__machine.add_transition("wait", "stop", "waiting")
        self.__machine.add_transition("heat", "waiting", "heating",
                                      conditions="filtration_allow_heating")
        self.__machine.add_transition("stop", ["waiting", "heating", "recovering"], "stop")
        self.__machine.add_transition("wait", "heating", "recovering")
        self.__machine.add_transition("wait", "recovering", "waiting")

    def setpoint(self, value):
        self.__setpoint = value
        logger.info("Setpoint set to %.1f" % self.__setpoint)
        # Hack. Restart the heating if the setpoint is changed
        if self.__next_start > datetime.now():
            self.__next_start -= timedelta(days=1)

    def start_hour(self, value):
        logger.info("Hour for heating start set to: %s" % value)
        tm = datetime.now()
        self.__next_start = tm.replace(hour=value, minute=0, second=0, microsecond=0)
        if self.__next_start < tm:
            self.__next_start += timedelta(days=1)

    def filtration_ready_for_heating(self):
        actor = self.get_actor("Filtration")
        return actor.is_eco_waiting().get() or actor.is_eco_normal().get()

    def filtration_allow_heating(self):
        actor = self.get_actor("Filtration")
        return actor.is_eco_heating().get()

    def check_before_on(self):
        temperature = self.__devices.get_sensor("temperature_pool").value
        return (temperature - Heating.HYSTERESIS_DOWN) < self.__setpoint

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__encoder.heating_state("stop")
        self.__devices.get_valve("heating").off()

    @do_repeat()
    def on_enter_waiting(self):
        logger.info("Entering waiting state")
        self.__devices.get_valve("heating").off()
        self.__encoder.heating_state("waiting")

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_waiting(self):
        now = datetime.now()
        if now >= self.__next_start:
            if self.filtration_ready_for_heating():
                if self.check_before_on():
                    self.get_actor("Filtration").eco_heating()
                    self._proxy.heat()
                    raise StopRepeatException
                else:
                    # No need to heat today. Schedule for next day
                    self.__next_start += timedelta(days=1)
                    logger.info("No heating needed today. Scheduled for %s" % self.__next_start)

    @do_repeat()
    def on_enter_heating(self):
        logger.info("Entering heating state")
        self.__encoder.heating_state("heating")
        self.__devices.get_valve("heating").on()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_heating(self):
        temperature = self.__devices.get_sensor("temperature_pool").value
        if temperature >= self.__setpoint + Heating.HYSTERESIS_UP:
            self.__next_start += timedelta(days=1)
            self._proxy.wait()
            raise StopRepeatException

    def on_exit_heating(self):
        self.__devices.get_valve("heating").off()
        actor = self.get_actor("Filtration")
        actor.eco()

    def on_enter_recovering(self):
        logger.info("Entering recovering state")
        self.__encoder.heating_state("recovering")
        self.do_delay(Heating.RECOVER_PERIOD, "wait")
