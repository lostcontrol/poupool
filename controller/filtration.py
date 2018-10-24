import pykka
from datetime import datetime, timedelta
import time
import logging
from astral import Astral
from .actor import PoupoolModel
from .actor import PoupoolActor
from .actor import StopRepeatException, repeat, do_repeat
from .util import round_timedelta, Timer

logger = logging.getLogger(__name__)


class EcoMode(object):

    def __init__(self, encoder):
        self.__encoder = encoder
        self.filtration = Timer("filtration")
        self.current = Timer("current")
        self.reset_hour = 0
        self.__period = 3
        self.tank_percentage = 0.1
        self.daily = timedelta(hours=10)
        self.period_duration = timedelta(hours=1)
        self.off_duration = timedelta()
        self.on_duration = timedelta()
        self.stir_duration = timedelta()
        self.tank_duration = timedelta()

    @property
    def reset_hour(self):
        return self.__next_reset

    @reset_hour.setter
    def reset_hour(self, hour):
        tm = datetime.now()
        self.__next_reset = tm.replace(hour=hour, minute=0, second=0, microsecond=0)
        if self.__next_reset < tm:
            self.__next_reset += timedelta(days=1)

    def __recompute_period_duration(self):
        self.period_duration = self.filtration.delay / self.period
        assert self.period_duration > timedelta()

    @property
    def period(self):
        return self.__period

    @period.setter
    def period(self, value):
        self.__period = value
        self.__recompute_period_duration()

    @property
    def daily(self):
        return self.filtration.delay

    @daily.setter
    def daily(self, value):
        self.filtration.delay = value
        self.__recompute_period_duration()

    def clear(self):
        self.filtration.clear()
        self.current.delay = timedelta()
        self.__encoder.filtration_next(str(round_timedelta(self.current.remaining)))

    def compute(self):
        remaining_duration = max(timedelta(), self.filtration.delay - self.filtration.duration)
        assert self.period_duration > timedelta()
        remaining_periods = max(1, int(remaining_duration / self.period_duration))
        remaining_time = max(timedelta(), self.reset_hour - datetime.now())
        logger.info("Remaining duration: %s periods: %d time: %s" %
                    (remaining_duration, remaining_periods, remaining_time))
        self.on_duration = min(remaining_time, remaining_duration / remaining_periods)
        if self.on_duration < timedelta(hours=1):
            self.on_duration = timedelta(hours=1)
        self.off_duration = (remaining_time - remaining_duration) / remaining_periods
        if self.off_duration < timedelta():
            self.off_duration = timedelta()
        self.tank_duration = self.tank_percentage * self.on_duration
        if self.tank_duration < timedelta(minutes=1):
            self.tank_duration = timedelta(minutes=1)
        if self.on_duration > self.tank_duration:
            self.on_duration -= self.tank_duration
        logger.info("Duration on: %s tank: %s off: %s" %
                    (self.on_duration, self.tank_duration, self.off_duration))

    def set_current(self, duration):
        self.current.delay = duration

    def update(self, now, factor=1):
        self.current.update(now)
        self.filtration.update(now, factor)
        self.__encoder.filtration_next(str(round_timedelta(self.current.remaining)))
        seconds = (self.filtration.delay - self.filtration.duration).total_seconds()
        remaining = max(timedelta(), timedelta(seconds=int(seconds)))
        self.__encoder.filtration_remaining(str(remaining))

    def elapsed_on(self):
        return self.current.elapsed() or self.filtration.elapsed()

    def elapsed_off(self):
        return self.current.elapsed() and not self.filtration.elapsed()

    def check_reset(self, now):
        if now >= self.__next_reset:
            self.__next_reset += timedelta(days=1)
            self.filtration.reset()
            return True
        return False


class StirMode(object):

    def __init__(self, devices):
        self.__devices = devices
        self.__stir_state = False
        self.__current = Timer("stir")
        self.__period = timedelta(seconds=3600)
        self.__duration = timedelta(seconds=120)
        # TODO Do not hard code this
        self.__astral = Astral()["Bern"]

    def stir_period(self, value):
        period = timedelta(seconds=value)
        if period > timedelta() and period < self.__duration:
            logger.error("Stir period must be greater than stir duration!!!")
        else:
            self.__period = period
            logger.info("Stir period set to: %s" % self.__period)

    def stir_duration(self, value):
        duration = timedelta(seconds=value)
        if self.__period > timedelta() and self.__period < duration:
            logger.error("Stir period must be greater than stir duration!!!")
        else:
            self.__duration = duration
            logger.info("Stir duration set to: %s" % self.__duration)

    def __pause(self):
        self.__stir_state = False
        self.__current.delay = max(timedelta(), self.__period - self.__duration)
        self.__devices.get_pump("boost").off()
        logger.info("Stir deactivated for %s" % self.__current.delay)

    def __stir(self):
        self.__stir_state = True
        self.__current.delay = self.__duration
        self.__devices.get_pump("boost").on()
        logger.info("Stir activated for %s" % self.__current.delay)

    def clear(self):
        self.__pause()

    def update(self, now):
        self.__current.update(now)
        # We only activate the stir mode if the sun elevation is greater than ~20°.
        # No need to stir at night, this mode is meant to lower the solar cover
        # temperature.
        if self.__astral.solar_elevation() >= 20:
            if self.__period > timedelta() and self.__current.elapsed():
                if self.__stir_state:
                    self.__pause()
                else:
                    self.__stir()


class Filtration(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    states = ["stop",
              "closing",
              {"name": "opening", "children": [
                  "standby",
                  "overflow"]},
              {"name": "eco", "initial": "compute", "children": [
                  "compute",
                  "normal",
                  "tank",
                  "heating",
                  "waiting"]},
              {"name": "standby", "initial": "normal", "children": [
                  "boost",
                  "normal"]},
              {"name": "overflow", "initial": "normal", "children": [
                  "boost",
                  "normal"]},
              "comfort",
              "sweep",
              "reload",
              {"name": "wash", "initial": "backwash", "children": [
                  "backwash",
                  "rinse"]},
              {"name": "wintering", "initial": "waiting", "children": [
                  "stir",
                  "waiting"]}]

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__devices = devices
        # Parameters
        self.__eco_mode = EcoMode(encoder)
        self.__stir_mode = StirMode(devices)
        self.__boost_duration = timedelta(minutes=5)
        self.__speed_standby = 1
        self.__speed_overflow = 4
        self.__backwash_backwash_duration = 120
        self.__backwash_rinse_duration = 60
        self.__backwash_period = 30
        self.__backwash_last = datetime.fromtimestamp(0)
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Filtration.states,
                                      initial="stop", before_state_change=[self.__before_state_change])
        # Transitions
        # Eco
        self.__machine.add_transition(
            "eco", ["standby", "overflow", "comfort", "opening"], "closing")
        # Special transition from stop to eco because we need to start the tank FSM. However, we
        # cannot start it on_exit of stop because when going from stop to wintering, the tank will
        # remain in the stop state.
        self.__machine.add_transition("eco", "stop", "eco", before=["tank_start", "heating_start"])
        self.__machine.add_transition("eco", ["eco_heating", "reload", "wash_rinse"], "eco")
        self.__machine.add_transition("closed", "closing", "eco")
        self.__machine.add_transition("eco_normal", ["eco_compute", "eco_waiting"], "eco_normal")
        self.__machine.add_transition("eco_tank", "eco_normal", "eco_tank", unless="tank_is_low")
        self.__machine.add_transition("eco_heating", ["eco_waiting", "eco_normal"], "eco_heating")
        self.__machine.add_transition("eco_waiting", ["eco_compute", "eco_tank"], "eco_waiting")
        self.__machine.add_transition("opened", "opening_standby", "standby_boost")
        self.__machine.add_transition("opened", "opening_overflow", "overflow_boost")
        # Standby
        self.__machine.add_transition(
            "standby", ["eco", "closing"], "opening_standby", unless="tank_is_low")
        self.__machine.add_transition(
            "standby", ["overflow", "comfort", "sweep", "reload"], "standby")
        self.__machine.add_transition("standby", "standby_boost", "standby_normal")
        # Overflow
        self.__machine.add_transition(
            "overflow", ["eco", "closing"], "opening_overflow", unless="tank_is_low")
        self.__machine.add_transition("overflow", ["standby", "comfort", "reload"], "overflow")
        self.__machine.add_transition("overflow", "overflow_boost", "overflow_normal")
        # Comfort
        self.__machine.add_transition("comfort", ["standby", "overflow"], "comfort")
        # Sweep
        self.__machine.add_transition("sweep", "standby", "sweep")
        # Stop
        self.__machine.add_transition(
            "stop", ["eco", "standby", "overflow", "comfort", "sweep", "opening", "closing", "wash", "wintering"], "stop")
        # (Back)wash
        self.__machine.add_transition(
            "wash", ["eco_normal", "eco_waiting"], "wash", conditions="tank_is_high")
        self.__machine.add_transition("rinse", "wash_backwash", "wash_rinse")
        # Wintering
        self.__machine.add_transition("wintering", "stop", "wintering")
        self.__machine.add_transition("wintering_waiting", "wintering_stir", "wintering_waiting")
        self.__machine.add_transition("wintering_stir", "wintering_waiting", "wintering_stir")
        # Hack to reload settings. Often the pumps/valves are set in the on_enter callback. In some
        # cases, we can change settings that needs to reload the same state. However, a transition
        # to the same state does not result in on_exit/on_enter being called again (sounds logic
        # since there is actually no state change). So we jump to the reload state and back to
        # workaround this.
        self.__machine.add_transition("reload", ["eco", "standby", "overflow"], "reload")
        #self.__machine.get_graph().draw("filtration.png", prog="dot")

    def __reload_eco(self):
        if self.is_eco(allow_substates=True):
            # Jump to the reload state so that we can jump back into the same state
            self._proxy.reload()
            self._proxy.eco()

    def duration(self, value):
        current_duration = self.__eco_mode.filtration.duration
        self.__eco_mode.daily = timedelta(seconds=value)
        logger.info("Duration for daily filtration set to: %s" % self.__eco_mode.daily)
        # Restore today's elapsed duration
        self.__eco_mode.filtration.duration = current_duration
        self.__reload_eco()

    def period(self, value):
        self.__eco_mode.period = value
        logger.info("Period(s) for filtration set to: %s" % self.__eco_mode.period)
        self.__reload_eco()

    def tank_percentage(self, value):
        self.__eco_mode.tank_percentage = value
        logger.info("Percentage for tank filtration set to: %s" % self.__eco_mode.tank_percentage)
        self.__reload_eco()

    def stir_duration(self, value):
        self.__stir_mode.stir_duration(value)

    def stir_period(self, value):
        self.__stir_mode.stir_period(value)

    def reset_hour(self, value):
        self.__eco_mode.reset_hour = value
        logger.info("Hour for daily filtration reset set to: %s" % self.__eco_mode.reset_hour.hour)
        self.__reload_eco()

    def boost_duration(self, value):
        self.__boost_duration = timedelta(seconds=value)
        logger.info("Duration for boost while going out of eco set to: %s" % self.__boost_duration)

    def speed_standby(self, value):
        self.__speed_standby = value
        logger.info("Speed for standby mode set to: %d" % self.__speed_standby)
        if self.is_standby_normal():
            # Jump to the reload state so that we can jump back into standby mode
            self._proxy.reload()
            self._proxy.standby()

    def speed_overflow(self, value):
        self.__speed_overflow = value
        logger.info("Speed for overflow mode set to: %d" % self.__speed_overflow)
        if self.is_overflow_normal():
            # Jump to the reload state so that we can jump back into overflow mode
            self._proxy.reload()
            self._proxy.overflow()

    def backwash_backwash_duration(self, value):
        self.__backwash_backwash_duration = timedelta(seconds=value)
        logger.info("Duration for backwash set to: %s" % self.__backwash_backwash_duration)

    def backwash_rinse_duration(self, value):
        self.__backwash_rinse_duration = timedelta(seconds=value)
        logger.info("Duration for rinse set to: %s" % self.__backwash_rinse_duration)

    def backwash_period(self, value):
        if value < 2:
            logger.error("We do not allow backwash everyday!!!")
        else:
            self.__backwash_period = value
            logger.info("Backwash period set to: %d" % self.__backwash_period)

    def backwash_last(self, value):
        self.__backwash_last = datetime.strptime(value, "%c")
        logger.info("Backwash last set to: %s" % self.__backwash_last)

    def tank_start(self):
        tank = self.get_actor("Tank")
        if tank.is_stop().get():
            tank.normal()

    def heating_start(self):
        heating = self.get_actor("Heating")
        if heating.is_stop().get():
            heating.wait()

    def tank_is_low(self):
        return self.get_actor("Tank").is_low().get()

    def tank_is_high(self):
        return self.get_actor("Tank").is_high().get()

    def __start_backwash(self):
        diff = datetime.now() - self.__backwash_last
        if diff >= timedelta(self.__backwash_period):
            if self.tank_is_high():
                logger.info("Time for a backwash and tank is high")
                return True
            else:
                logger.debug("Time for a backwash but tank is NOT HIGH")
        return False

    def __before_state_change(self):
        self.__eco_mode.clear()

    def __disinfection_start(self):
        self.__actor_run("Disinfection")

    def __actor_run(self, name):
        actor = self.get_actor(name)
        if actor.is_stop().get():
            actor.run()

    def __actor_stop(self, name):
        actor = self.get_actor(name)
        if not actor.is_stop().get():
            actor.stop()

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__encoder.filtration_state("stop")
        self.__actor_stop("Disinfection")
        self.__actor_stop("Tank")
        self.__actor_stop("Arduino")
        self.__devices.get_pump("variable").off()
        self.__devices.get_pump("boost").off()
        self.__devices.get_valve("gravity").off()
        self.__devices.get_valve("backwash").off()
        self.__devices.get_valve("tank").off()
        self.__devices.get_valve("drain").off()

    def on_exit_stop(self):
        logger.info("Exiting stop state")
        self.__actor_run("Arduino")

    @do_repeat()
    def on_enter_closing(self):
        logger.info("Entering closing state")
        self.__encoder.filtration_state("closing")
        # stop the pumps to avoid perturbation in the water while shutter is moving
        self.__devices.get_valve("gravity").on()
        self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").off()
        # close the roller shutter
        self.get_actor("Arduino").cover_close()

    @repeat(delay=5)
    def do_repeat_closing(self):
        position = self.get_actor("Arduino").cover_position().get()
        logger.debug("Cover position is %d" % position)
        if position == 0:
            # Because of roundings, the cover might still need to move just a little more.
            # We wait a bit more before exiting the state.
            self._proxy.do_delay(2, "closed")
            raise StopRepeatException

    def on_exit_closing(self):
        logger.info("Exiting closing state")
        # stop the roller shutter
        self.get_actor("Arduino").cover_stop()

    @do_repeat()
    def on_enter_opening(self):
        logger.info("Entering opening state")
        self.__encoder.filtration_state("opening")
        self.__actor_stop("Disinfection")
        # stop the pumps to avoid perturbation in the water while shutter is moving
        self.__devices.get_valve("gravity").on()
        self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").off()
        # open the roller shutter
        self.get_actor("Arduino").cover_open()

    @repeat(delay=5)
    def do_repeat_opening(self):
        position = self.get_actor("Arduino").cover_position().get()
        logger.debug("Cover position is %d" % position)
        if position == 100:
            # Because of roundings, the cover might still need to move just a little more.
            # We wait a bit more before exiting the state.
            self._proxy.do_delay(2, "opened")
            raise StopRepeatException

    def on_exit_opening(self):
        logger.info("Exiting opening state")
        # TODO I'm not quite sure why this is here!!!??? Needed? Bug?
        self.get_actor("Tank").set_mode("overflow")
        # stop the roller shutter
        self.get_actor("Arduino").cover_stop()

    def on_enter_eco(self):
        logger.info("Entering eco state")
        self.__actor_stop("Light")
        self.__devices.get_valve("drain").off()
        self.__devices.get_valve("gravity").on()
        self.__devices.get_valve("tank").off()
        self.get_actor("Tank").set_mode("eco")

    def on_enter_eco_compute(self):
        logger.info("Entering eco compute")
        self.__encoder.filtration_state("eco_compute")
        self.__eco_mode.check_reset(datetime.now())
        self.__eco_mode.compute()
        if self.__eco_mode.off_duration.total_seconds() > 0:
            self._proxy.do_delay(10, "eco_waiting")
        elif self.__eco_mode.on_duration.total_seconds() > 0:
            self._proxy.do_delay(10, "eco_normal")
        else:
            self._proxy.do_delay(10, "eco_waiting")

    @do_repeat()
    def on_enter_eco_normal(self):
        logger.info("Entering eco_normal state")
        self.__encoder.filtration_state("eco_normal")
        self.__eco_mode.set_current(self.__eco_mode.on_duration)
        self.__disinfection_start()
        self.__devices.get_pump("variable").speed(1)

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_normal(self):
        if self.__start_backwash():
            self._proxy.wash()
            raise StopRepeatException
        now = datetime.now()
        self.__eco_mode.update(now)
        if self.__eco_mode.check_reset(now):
            self.__reload_eco()
            raise StopRepeatException
        if self.__eco_mode.elapsed_on():
            if self.tank_is_low():
                self._proxy.eco_waiting()
            elif self.__eco_mode.tank_duration > timedelta():
                self._proxy.eco_tank()
            raise StopRepeatException

    @do_repeat()
    def on_enter_eco_tank(self):
        logger.info("Entering eco_tank state")
        self.__encoder.filtration_state("eco_tank")
        self.__eco_mode.set_current(self.__eco_mode.tank_duration)
        self.__actor_stop("Disinfection")
        self.__devices.get_valve("tank").on()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_tank(self):
        now = datetime.now()
        self.__eco_mode.update(now)
        if self.__eco_mode.check_reset(now):
            self.__reload_eco()
            raise StopRepeatException
        if self.__eco_mode.elapsed_on():
            self._proxy.eco_waiting()
            raise StopRepeatException

    def on_exit_eco_tank(self):
        self.__devices.get_valve("tank").off()

    @do_repeat()
    def on_enter_eco_heating(self):
        logger.info("Entering eco_heating state")
        self.__encoder.filtration_state("eco_heating")
        self.__eco_mode.clear()
        self.__disinfection_start()
        self.__devices.get_pump("variable").speed(2)

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_heating(self):
        now = datetime.now()
        # We are running at speed 2 so count a bit more than 1 for the filteration
        self.__eco_mode.update(now, 1.1)
        # Check if we have to reset the filtration per day counter but do not react
        # since heating has an higher priority.
        self.__eco_mode.check_reset(now)

    def on_exit_eco_heating(self):
        actor = self.get_actor("Heating")
        if actor.is_heating().get():
            actor.wait()

    @do_repeat()
    def on_enter_eco_waiting(self):
        logger.info("Entering eco_waiting state")
        self.__encoder.filtration_state("eco_waiting")
        self.__eco_mode.set_current(self.__eco_mode.off_duration)
        self.__actor_stop("Disinfection")
        self.__devices.get_pump("variable").off()
        self.__stir_mode.clear()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_eco_waiting(self):
        if self.__start_backwash():
            self._proxy.wash()
            raise StopRepeatException
        now = datetime.now()
        self.__eco_mode.update(now, 0)
        if self.__eco_mode.check_reset(now):
            self.__reload_eco()
            raise StopRepeatException
        if self.__eco_mode.elapsed_off():
            self._proxy.eco_normal()
            raise StopRepeatException
        # Update the stir mode at the end so we do not switch the boost pumps
        # for nothing.
        self.__stir_mode.update(now)

    def on_exit_eco_waiting(self):
        logger.info("Exiting eco_waiting state")
        self.__stir_mode.clear()

    def on_enter_standby(self):
        logger.info("Entering standby state")
        self.__devices.get_valve("gravity").off()

    def on_enter_standby_boost(self):
        logger.info("Entering standby boost state")
        self.__encoder.filtration_state("standby_boost")
        self.__devices.get_valve("tank").on()
        self.__devices.get_pump("boost").on()
        self.__devices.get_pump("variable").speed(3)
        self._proxy.do_delay(self.__boost_duration.total_seconds(), "standby")

    @do_repeat()
    def on_enter_standby_normal(self):
        logger.info("Entering standby state")
        self.__encoder.filtration_state("standby")
        if self.__speed_standby > 0:
            self.__devices.get_valve("tank").on()
        else:
            self.__devices.get_valve("tank").off()
        self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").speed(self.__speed_standby)

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_standby_normal(self):
        now = datetime.now()
        factor = 1 if self.__speed_standby > 0 else 0
        self.__eco_mode.update(now, factor)

    def on_enter_sweep(self):
        logger.info("Entering sweep state")
        self.__encoder.filtration_state("sweep")
        self.__devices.get_valve("gravity").on()
        self.__devices.get_valve("tank").off()
        self.__devices.get_pump("variable").speed(3)
        self.__devices.get_pump("boost").off()

    def on_exit_sweep(self):
        logger.info("Exiting sweep state")

    @do_repeat()
    def on_enter_comfort(self):
        logger.info("Entering comfort state")
        self.__encoder.filtration_state("comfort")
        self.__devices.get_valve("gravity").off()
        self.__devices.get_valve("tank").off()
        self.__devices.get_pump("variable").speed(2)
        self.__devices.get_pump("boost").off()

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_comfort(self):
        now = datetime.now()
        self.__eco_mode.update(now, 1)
        actor = self.get_actor("Heating")
        if not actor.is_forcing().get() and not actor.is_recovering().get():
            actor.force()

    def on_exit_comfort(self):
        logger.info("Exiting comfort state")
        self.get_actor("Heating").wait()

    def on_enter_overflow(self):
        logger.info("Entering overflow state")
        self.__devices.get_valve("gravity").off()
        self.__devices.get_valve("tank").on()

    def on_enter_overflow_boost(self):
        logger.info("Entering overflow boost state")
        self.__encoder.filtration_state("overflow_boost")
        self.__devices.get_pump("variable").speed(3)
        self.__devices.get_pump("boost").on()
        self._proxy.do_delay(self.__boost_duration.total_seconds(), "overflow")

    @do_repeat()
    def on_enter_overflow_normal(self):
        logger.info("Entering overflow state")
        self.__encoder.filtration_state("overflow")
        speed = self.__speed_overflow
        self.__devices.get_pump("variable").speed(min(speed, 3))
        if speed > 3:
            self.__devices.get_pump("boost").on()
        else:
            self.__devices.get_pump("boost").off()
        # Use a constant chlorine flow
        self.get_actor("Disinfection").constant()

    def on_exit_overflow_normal(self):
        logger.info("Exiting overflow state")
        self.__actor_stop("Swim")
        self.__actor_stop("Disinfection")

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_overflow_normal(self):
        now = datetime.now()
        self.__eco_mode.update(now, 2 if self.__speed_overflow > 2 else 1)

    def on_enter_wash(self):
        logger.info("Entering wash state")
        self.__actor_stop("Disinfection")

    def on_enter_wash_backwash(self):
        logger.info("Entering backwash state")
        self.__encoder.filtration_state("backwash")
        self.__devices.get_valve("tank").on()
        self.__devices.get_pump("variable").speed(3)
        time.sleep(2)
        self.__devices.get_valve("backwash").on()
        time.sleep(2)
        self.__devices.get_valve("drain").on()
        self._proxy.do_delay(self.__backwash_backwash_duration.total_seconds(), "rinse")

    def on_enter_wash_rinse(self):
        logger.info("Entering rinse state")
        self.__encoder.filtration_state("rinse")
        self.__devices.get_valve("backwash").off()
        self._proxy.do_delay(self.__backwash_rinse_duration.total_seconds(), "eco")

    def on_exit_wash_rinse(self):
        logger.info("Exiting rinse state")
        self.__devices.get_pump("variable").speed(1)
        self.__backwash_last = datetime.now()
        self.__encoder.filtration_backwash_last(self.__backwash_last.strftime("%c"), retain=True)

    def on_enter_wintering(self):
        logger.info("Entering wintering state")
        self.get_actor("Heater").wait()
        # open the roller shutter

    def on_enter_wintering_waiting(self):
        logger.info("Entering wintering waiting state")
        self.__encoder.filtration_state("wintering_waiting")
        # self.__devices.get_pump("boost").off()
        self.__devices.get_pump("variable").off()
        self._proxy.do_delay(3 * 3600, "wintering_stir")

    def on_enter_wintering_stir(self):
        logger.info("Entering wintering stir state")
        self.__encoder.filtration_state("wintering_stir")
        # self.__devices.get_pump("boost").on()
        self.__devices.get_pump("variable").speed(1)
        self._proxy.do_delay(30 * 60, "wintering_waiting")

    def on_exit_wintering(self):
        logger.info("Exiting wintering state")
        self.__actor_stop("Heater")
        self.__actor_stop("Swim")
