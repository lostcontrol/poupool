import pykka
import datetime
import time
import logging
from .actor import PoupoolModel
from .actor import PoupoolActor
from .actor import StopRepeatException, repeat, do_repeat, Timer

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
        if not self.__start:
            self.__start = now
        if now - self.__start > datetime.timedelta(days=1):
            # reset
            self.__reset()
        elif self.__last:
            self.__duration += factor * (now - self.__last)
            remaining = max(datetime.timedelta(), self.daily - self.__duration)
            logger.debug("(%s) Duration since last reset: %s Remaining: %s" %
                         (self.__name, self.__duration, remaining))
        if factor != 0:
            self.__last = now

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

    states = ["stop",
              "closing",
              {"name": "opening", "children": [
                  "standby",
                  "overflow"]},
              {"name": "eco", "initial": "normal", "children": [
                  "normal",
                  "tank",
                  "stir",
                  "waiting"]},
              "standby",
              "overflow",
              {"name": "wash", "initial": "backwash", "children": [
                  "backwash",
                  "rinse"]}]

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__devices = devices
        # Parameters
        self.__duration = Duration("filtration")
        self.__tank_duration = Duration("tank")
        self.__stir_duration = datetime.timedelta()
        self.__stir_timer = Timer("stir")
        self.__speed_standby = 1
        self.__speed_overflow = 4
        self.__backwash_period = 30
        self.__backwash_margin = 5
        self.__backwash_last = datetime.datetime.fromtimestamp(0)
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Filtration.states,
                                      initial="stop", before_state_change=[self.__before_state_change])
        # Transitions
        self.__machine.add_transition("eco", "stop", "eco")
        self.__machine.add_transition("eco", ["standby", "overflow", "opening"], "closing")
        self.__machine.add_transition("eco", "wash_rinse", "eco")
        self.__machine.add_transition("closed", "closing", "eco")
        self.__machine.add_transition("eco_tank", "eco_normal", "eco_tank", unless="tank_is_low")
        self.__machine.add_transition("eco_stir", "eco_normal", "eco_stir")
        self.__machine.add_transition("eco_normal", "eco", "eco_normal")
        self.__machine.add_transition("eco_waiting", "eco_normal", "eco_waiting")
        self.__machine.add_transition("standby", ["eco", "closing"], "opening_standby")
        self.__machine.add_transition("standby", "overflow", "standby")
        self.__machine.add_transition("opened", "opening_standby", "standby")
        self.__machine.add_transition("opened", "opening_overflow", "overflow")
        self.__machine.add_transition(
            "overflow", ["eco", "closing"], "opening_overflow", unless="tank_is_low")
        self.__machine.add_transition("overflow", "standby", "overflow", unless="tank_is_low")
        self.__machine.add_transition(
            "stop", ["eco", "standby", "overflow", "opening", "closing", "wash"], "stop")
        self.__machine.add_transition(
            "wash", ["eco_normal", "eco_waiting"], "wash", conditions="tank_is_high")
        self.__machine.add_transition("rinse", "wash_backwash", "wash_rinse")
        #self.__machine.get_graph().draw("filtration.png", prog="dot")

    def duration(self, value):
        self.__duration.daily = datetime.timedelta(seconds=value)
        logger.info("Duration for daily filtration set to: %s" % self.__duration.daily)

    def tank_duration(self, value):
        self.__tank_duration.daily = datetime.timedelta(seconds=value)
        logger.info("Duration for daily tank filtration set to: %s" % self.__tank_duration.daily)

    def stir_duration(self, value):
        self.__stir_duration = datetime.timedelta(seconds=value)
        logger.info("Duration for pool stirring in eco set to: %s" % self.__stir_duration)

    def hour_of_reset(self, value):
        self.__duration.hour = value
        self.__tank_duration.hour = value
        logger.info("Hour for daily filtration reset set to: %s" % self.__duration.hour)

    def speed_standby(self, value):
        self.__speed_standby = value
        logger.info("Speed for standby mode set to: %d" % self.__speed_standby)
        if self.is_standby():
            self._proxy.standby()

    def speed_overflow(self, value):
        self.__speed_overflow = value
        logger.info("Speed for overflow mode set to: %d" % self.__speed_overflow)
        if self.is_overflow():
            self._proxy.overflow()

    def backwash_period(self, value):
        if value - self.__backwash_margin < 2:
            logger.error("We do not allow backwash everyday!!!")
        else:
            self.__backwash_period = value
            logger.info("Backwash period set to: %d" % self.__backwash_period)

    def backwash_margin(self, value):
        if self.__backwash_period - value < 2:
            logger.error("We do not allow backwash everyday!!!")
        else:
            self.__backwash_margin = value
            logger.info("Backwash margin set to: %d" % self.__backwash_margin)

    def backwash_last(self, value):
        self.__backwash_last = datetime.datetime.strptime(value, "%c")
        logger.info("Backwash last set to: %s" % self.__backwash_last)

    def tank_is_low(self):
        return self.get_actor("Tank").is_low().get()

    def tank_is_high(self):
        return self.get_actor("Tank").is_high().get()

    def __start_backwash(self):
        days = self.__backwash_period
        margin = self.__backwash_margin
        diff = datetime.datetime.now() - self.__backwash_last
        if datetime.timedelta(days - margin) < diff < datetime.timedelta(days + margin):
            if self.tank_is_high():
                logger.info("Time for a backwash and tank is high")
                return True
            else:
                logger.debug("Time for a backwash but tank is NOT HIGH")
        return False

    def __before_state_change(self):
        self.__duration.clear()
        self.__tank_duration.clear()

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__encoder.filtration_state("stop")
        self.get_actor("Tank").stop()
        self.__devices.get_pump("variable").off()
        self.__devices.get_pump("boost").off()
        self.__devices.get_valve("gravity").off()
        self.__devices.get_valve("backwash").off()
        self.__devices.get_valve("tank").off()
        self.__devices.get_valve("drain").off()

    def on_exit_stop(self):
        logger.info("Exiting stop state")
        self.get_actor("Disinfection").run()
        self.get_actor("Tank").normal()

    def on_enter_closing(self):
        logger.info("Entering closing state")
        self.__encoder.filtration_state("closing")
        # stop the pumps to avoid perturbation in the water while shutter is moving
        self.__devices.get_valve("gravity").on()
        self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").off()
        # close the roller shutter
        self.do_delay(5, "closed")

    def on_exit_closing(self):
        logger.info("Exiting closing state")
        # stop the roller shutter

    def on_enter_opening(self):
        logger.info("Entering opening state")
        self.__encoder.filtration_state("opening")
        # stop the pumps to avoid perturbation in the water while shutter is moving
        self.__devices.get_valve("gravity").on()
        self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").off()
        # open the roller shutter
        self.do_delay(5, "opened")

    def on_exit_opening(self):
        logger.info("Exiting opening state")
        self.get_actor("Tank").set_mode("overflow")
        # stop the roller shutter

    def on_enter_eco(self):
        logger.info("Entering eco state")
        self.__devices.get_valve("drain").off()
        self.get_actor("Tank").set_mode("eco")

    @do_repeat()
    def on_enter_eco_normal(self):
        logger.info("Entering eco_normal state")
        self.__encoder.filtration_state("eco_normal")
        self.__devices.get_valve("tank").off()
        self.__devices.get_valve("gravity").on()
        self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").speed(1)
        self.__stir_timer.delay = datetime.timedelta(hours=1) - self.__stir_duration

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_normal(self):
        now = datetime.datetime.now()
        self.__duration.update(now)
        self.__tank_duration.update(now, 0)
        self.__stir_timer.update(now)
        if self.__start_backwash():
            self._proxy.wash()
            raise StopRepeatException
        if self.__stir_timer.elapsed():
            self._proxy.eco_stir()
            raise StopRepeatException
        if not self.__tank_duration.elapsed():
            self._proxy.eco_tank()
            raise StopRepeatException
        if self.__duration.elapsed():
            self._proxy.eco_waiting()
            raise StopRepeatException

    @do_repeat()
    def on_enter_eco_waiting(self):
        logger.info("Entering eco_waiting state")
        self.__encoder.filtration_state("eco_waiting")
        self.__devices.get_pump("variable").off()
        self.__devices.get_pump("boost").off()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_waiting(self):
        now = datetime.datetime.now()
        self.__duration.update(now, 0)
        self.__tank_duration.update(now, 0)
        if self.__start_backwash():
            self._proxy.wash()
            raise StopRepeatException
        if not self.__duration.elapsed():
            self._proxy.eco_normal()
            raise StopRepeatException

    @do_repeat()
    def on_enter_eco_stir(self):
        logger.info("Entering eco_stir state")
        self.__encoder.filtration_state("eco_stir")
        self.__devices.get_pump("boost").on()
        self.__stir_timer.delay = self.__stir_duration

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_stir(self):
        now = datetime.datetime.now()
        self.__duration.update(now)
        self.__tank_duration.update(now, 0)
        self.__stir_timer.update(now)
        if self.__stir_timer.elapsed():
            self._proxy.eco_normal()
            raise StopRepeatException

    @do_repeat()
    def on_enter_eco_tank(self):
        logger.info("Entering eco_tank state")
        self.__encoder.filtration_state("eco_tank")
        self.__devices.get_valve("tank").on()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_tank(self):
        now = datetime.datetime.now()
        self.__duration.update(now)
        self.__tank_duration.update(now)
        if self.__tank_duration.elapsed():
            self._proxy.eco_normal()
            raise StopRepeatException

    @do_repeat()
    def on_enter_standby(self):
        logger.info("Entering standby state")
        self.__encoder.filtration_state("standby")
        self.__devices.get_valve("gravity").off()
        if self.__speed_standby > 0:
            self.__devices.get_valve("tank").on()
        else:
            self.__devices.get_valve("tank").off()
        self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").speed(self.__speed_standby)

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_standby(self):
        now = datetime.datetime.now()
        self.__duration.update(now, 1 if self.__speed_standby > 0 else 0)
        self.__tank_duration.update(now, 0)

    @do_repeat()
    def on_enter_overflow(self):
        logger.info("Entering overflow state")
        self.__encoder.filtration_state("overflow")
        self.__devices.get_valve("gravity").off()
        speed = self.__speed_overflow
        self.__devices.get_pump("variable").speed(min(speed, 3))
        if speed > 3:
            self.__devices.get_pump("boost").on()
        self.__devices.get_valve("tank").on()

    def on_exit_overflow(self):
        logger.info("Exiting overflow state")
        swim = self.get_actor("Swim")
        if swim and not swim.is_stop().get():
            swim.stop()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_overflow(self):
        now = datetime.datetime.now()
        self.__duration.update(now, 2)
        self.__tank_duration.update(now)

    def on_enter_wash_backwash(self):
        logger.info("Entering backwash state")
        self.__encoder.filtration_state("backwash")
        self.__devices.get_valve("tank").on()
        self.__devices.get_pump("variable").speed(3)
        time.sleep(2)
        self.__devices.get_valve("backwash").on()
        time.sleep(5)
        self.__devices.get_valve("drain").on()
        self._proxy.do_delay(3 * 6, "rinse")

    def on_enter_wash_rinse(self):
        logger.info("Entering rinse state")
        self.__encoder.filtration_state("rinse")
        self.__devices.get_valve("backwash").off()
        self._proxy.do_delay(1 * 6, "eco")

    def on_exit_wash_rinse(self):
        self.__backwash_last = datetime.datetime.now()
        self.__encoder.filtration_backwash_last(self.__backwash_last.strftime("%c"), retain=True)
