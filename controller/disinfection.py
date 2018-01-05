import pykka
import time
from datetime import datetime, timedelta
import logging
from .actor import PoupoolModel
from .actor import PoupoolActor
from .actor import StopRepeatException, repeat, do_repeat
from .util import mapping, constrain, Timer

logger = logging.getLogger(__name__)


class PWM(PoupoolActor):

    def __init__(self, name, pump, period=10):
        super().__init__()
        self.__name = name
        self.__pump = pump
        self.__period = period
        self.__last = None
        self.__duration = 0
        self.__state = False
        self.__security_duration = Timer("PWM for %s" % name)
        self.__security_duration.delay = timedelta(seconds=3600)
        self.__security_reset = datetime.now() + timedelta(days=1)
        self.value = 0.0

    @repeat(delay=1)
    def do_run(self):
        now = time.time()
        if self.__last:
            diff = now - self.__last
            self.__duration += diff
            self.__duration = constrain(self.__duration, 0, self.__period)
            duty_on = self.value * self.__period
            duty_off = self.__period - duty_on
            duty = duty_on if self.__state else duty_off
            # Only print every 5 seconds
            if int(now) % 5 == 0:
                logger.debug("%s duty (on/off): %.1f/%.1f state: %d duration: %.1f" %
                             (self.__name, duty_on, duty_off, self.__state, self.__duration))
            if self.__state:
                self.__security_duration.update(datetime.now())
                if self.__duration > duty_on:
                    self.__duration = 0
                    self.__state = False
                    self.__pump.off()
            else:
                self.__security_duration.update(datetime.now(), 0)
                if self.__duration > duty_off and not self.__security_duration.elapsed():
                    self.__duration = 0
                    self.__state = True
                    self.__pump.on()
        if datetime.now() > self.__security_reset:
            self.__security_duration.reset()
            self.__security_reset += timedelta(days=1)
        self.__last = now


class PController(object):

    def __init__(self, pterm=0.1):
        self.setpoint = 0
        self.current = 0
        self.pterm = pterm

    def compute(self):
        error = self.setpoint - self.current
        return constrain(self.pterm * error, 0, 1)


class Disinfection(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    states = [
        "stop",
        "waiting",
        {"name": "running", "initial": "measuring", "children": [
            "measuring",
            "adjusting",
            "waiting"]}]

    def __init__(self, encoder, devices, disable=False):
        super().__init__()
        self.__is_disable = disable
        self.__encoder = encoder
        self.__devices = devices
        self.__measures = []
        self.__ph = PWM.start("pH", self.__devices.get_pump("ph")).proxy()
        self.__ph_controller = PController(pterm=-1.0)
        self.__ph_controller.setpoint = 7
        self.__cl = PWM.start("cl", self.__devices.get_pump("cl")).proxy()
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Disinfection.states, initial="stop")

        self.__machine.add_transition("run", "stop", "waiting", unless="is_disable")
        self.__machine.add_transition("run", "waiting", "running")
        self.__machine.add_transition("stop", ["waiting", "running"], "stop")
        self.__machine.add_transition("measure", "running_waiting", "running_measuring")
        self.__machine.add_transition("adjust", "running_measuring", "running_adjusting")
        self.__machine.add_transition("wait", "running_adjusting", "running_waiting")

    def ph_setpoint(self, value):
        self.__ph_controller.setpoint = value
        logger.info("pH setpoint set to: %f" % self.__ph_controller.setpoint)

    def ph_pterm(self, value):
        # We assume here that we use "pH minus" chemicals, therefore inverse the term.
        self.__ph_controller.pterm = -value
        logger.info("pH pterm set to: %f" % self.__ph_controller.pterm)

    def is_disable(self):
        return self.__is_disable

    def on_enter_stop(self):
        logger.info("Entering stop state")

    def on_enter_waiting(self):
        logger.info("Entering waiting state")
        self._proxy.do_delay(6, "run")

    def on_enter_running(self):
        self.__ph.do_run()
        self.__cl.do_run()

    def on_exit_running(self):
        self.__ph.value = 0
        self.__cl.value = 0
        self.__ph.do_cancel()
        self.__cl.do_cancel()
        self.__devices.get_pump("ph").off()
        self.__devices.get_pump("cl").off()

    @do_repeat()
    def on_enter_running_measuring(self):
        logger.info("Entering measuring state")
        self.__encoder.disinfection_state("measuring")
        self.__ph_measures = []

    @repeat(delay=2)
    def do_repeat_running_measuring(self):
        self.__ph_measures.append(self.__devices.get_sensor("ph").value)
        if len(self.__ph_measures) > 3:
            self._proxy.adjust()
            raise StopRepeatException

    def on_enter_running_adjusting(self):
        logger.info("Entering adjusting state")
        self.__encoder.disinfection_state("adjusting")
        ph = sum(self.__ph_measures) / len(self.__ph_measures)
        self.__encoder.disinfection_ph_value("%.1f" % ph)
        self.__ph_controller.current = ph
        ph_feedback = self.__ph_controller.compute()
        self.__encoder.disinfection_ph_feedback(int(round(ph_feedback * 100)))
        logger.info("pH: %f feedback: %f" % (ph, ph_feedback))
        self.__ph.value = ph_feedback
        self._proxy.wait()

    def on_enter_running_waiting(self):
        logger.info("Entering waiting state")
        self.__encoder.disinfection_state("waiting")
        self._proxy.do_delay(10, "measure")
