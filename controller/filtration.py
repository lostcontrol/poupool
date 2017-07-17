import pykka
import datetime
import logging
#from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolModel
from .actor import PoupoolActor
from .actor import StopRepeatException, repeat, do_repeat

logger = logging.getLogger(__name__)


class Duration(object):

    def __init__(self, name):
        self.__duration = datetime.timedelta()
        self.__name = name
        self.__start = None
        self.__last = None
        self.daily = datetime.timedelta()
        self.hour = 0

    def clear(self):
        self.__last = None

    def update(self, now, factor=1.0):
        if self.__last:
            diff = now - self.__last
            self.__duration += factor * diff
            if now - self.__start > datetime.timedelta(days=1):
                # reset
                self.__reset()
        if not self.__start:
            self.__start = now
        self.__last = now
        remaining = max(datetime.timedelta(), self.daily - self.__duration)
        logger.debug("(%s) Duration since last reset: %s Remaining: %s" %
                     (self.__name, self.__duration, remaining))

    def __reset(self):
        tm = datetime.datetime.now()
        self.__start = tm.replace(hour=self.hour, minute=0, second=0, microsecond=0)
        logger.info("(%s) Duration reset: %s Duration done: %s" %
                    (self.__name, self.__start, self.__duration))
        self.__duration = datetime.timedelta()

    def elapsed(self):
        return self.__duration >= self.daily


class Filtration(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    states = ["stop", "waiting", "eco", "eco_tank", "overflow"]

    def __init__(self, encoder, devices):
        super(Filtration, self).__init__()
        self.__encoder = encoder
        self.__devices = devices
        self.__duration = Duration("filtration")
        self.__tank_duration = Duration("tank")
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Filtration.states, initial="stop")
        # Transitions
        self.__machine.add_transition("eco", "stop", "eco")
        self.__machine.add_transition("eco", "waiting", "eco")
        self.__machine.add_transition("eco", "overflow", "eco")
        self.__machine.add_transition("eco", "eco_tank", "eco")
        self.__machine.add_transition("eco_tank", "eco", "eco_tank", unless="tank_is_low")
        self.__machine.add_transition("waiting", "eco", "waiting")
        self.__machine.add_transition("overflow", "eco", "overflow", unless="tank_is_low")
        self.__machine.add_transition("overflow", "waiting", "overflow", unless="tank_is_low")
        self.__machine.add_transition("stop", "eco", "stop")
        self.__machine.add_transition("stop", "eco_tank", "stop")
        self.__machine.add_transition("stop", "waiting", "stop")
        self.__machine.add_transition("stop", "overflow", "stop")

    def duration(self, value):
        self.__duration.daily = datetime.timedelta(seconds=value)
        logger.info("Duration for daily filtration set to: %s" % self.__duration.daily)

    def tank_duration(self, value):
        self.__tank_duration.daily = datetime.timedelta(seconds=value)
        logger.info("Duration for daily tank filtration set to: %s" % self.__tank_duration.daily)

    def hour_of_reset(self, value):
        self.__duration.hour = value
        self.__tank_duration.hour = value
        logger.info("Hour for daily filtration reset set to: %s" % self.__duration.hour)

    def tank_is_low(self):
        tank = self.get_actor("Tank")
        if tank:
            return tank.is_low().get()
        return False

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__encoder.filtration_state("stop")
        self.__duration.clear()
        tank = self.get_actor("Tank")
        if tank:
            tank.stop()
        self.__devices.get_pump("variable").off()
        self.__devices.get_pump("boost").off()
        self.__devices.get_valve("gravity").off()
        self.__devices.get_valve("backwash").off()
        self.__devices.get_valve("tank").off()
        self.__devices.get_valve("drain").off()

    def on_exit_stop(self):
        logger.info("Exiting stop state")
        tank = self.get_actor("Tank")
        if tank:
            tank.normal()

    @do_repeat()
    def on_enter_waiting(self):
        logger.info("Entering waiting state")
        self.__encoder.filtration_state("waiting")
        self.__duration.clear()
        self.__tank_duration.clear()
        self.__devices.get_pump("variable").off()
        self.__devices.get_pump("boost").off()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_waiting(self):
        if not self.__duration.elapsed():
            self._proxy.eco()
            raise StopRepeatException

    @do_repeat()
    def on_enter_eco(self):
        logger.info("Entering eco state")
        self.__encoder.filtration_state("eco")
        self.__tank_duration.clear()
        self.__devices.get_valve("tank").off()
        self.__devices.get_valve("gravity").on()
        self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").speed(1)

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco(self):
        self.__duration.update(datetime.datetime.now())
        if not self.__tank_duration.elapsed():
            self._proxy.eco_tank()
            raise StopRepeatException
        if self.__duration.elapsed():
            self._proxy.waiting()
            raise StopRepeatException

    @do_repeat()
    def on_enter_eco_tank(self):
        logger.info("Entering eco_tank state")
        self.__encoder.filtration_state("eco_tank")
        self.__devices.get_valve("tank").on()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_tank(self):
        self.__duration.update(datetime.datetime.now())
        self.__tank_duration.update(datetime.datetime.now())
        if self.__tank_duration.elapsed():
            self._proxy.eco()
            raise StopRepeatException

    @do_repeat()
    def on_enter_overflow(self):
        logger.info("Entering overflow state")
        self.__encoder.filtration_state("overflow")
        self.__devices.get_valve("gravity").off()
        self.__devices.get_valve("tank").on()
        self.__devices.get_pump("variable").speed(3)
        self.__devices.get_pump("boost").on()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_overflow(self):
        self.__duration.update(datetime.datetime.now(), 2)
        self.__tank_duration.update(datetime.datetime.now())
