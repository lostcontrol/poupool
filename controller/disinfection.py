import pykka
import time
import datetime
import logging
from .actor import PoupoolModel
from .actor import PoupoolActor
from .actor import StopRepeatException, repeat, do_repeat, Timer
from .util import mapping, constrain, Duration


logger = logging.getLogger(__name__)


class PWM(PoupoolActor):

    def __init__(self, name, pump, period=10):
        super().__init__()
        self.__pump = pump
        self.__period = period
        self.__last = None
        self.__duration = 0
        self.__state = False
        self.__security_duration = Duration("PWM for %s" % name)
        self.__security_duration.daily = datetime.timedelta(seconds=3600)
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
            #print("duty:%f state:%d duration:%f" % (duty, self.__state, self.__duration))
            if self.__state:
                self.__security_duration.update(datetime.datetime.now())
                if self.__duration > duty_on:
                    self.__duration = 0
                    self.__state = False
                    self.__pump.off()
            else:
                self.__security_duration.update(datetime.datetime.now(), 0)
                if self.__duration > duty_off and not self.__security_duration.elapsed():
                    self.__duration = 0
                    self.__state = True
                    self.__pump.on()
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
        self.__ph_controller = PController(pterm=-1.5)
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
        self.__ph_measures = []

    @repeat(delay=2)
    def do_repeat_running_measuring(self):
        #ph = self.__devices.get_sensor("ph").value
        import random
        self.__ph_measures.append(random.uniform(6.5, 8.5))
        if len(self.__ph_measures) > 5:
            self._proxy.adjust()
            raise StopRepeatException

    def on_enter_running_adjusting(self):
        logger.info("Entering adjusting state")
        ph = sum(self.__ph_measures) / len(self.__ph_measures)
        self.__ph_controller.current = ph
        ph_feedback = self.__ph_controller.compute()
        logger.info("pH: %f feedback: %f" % (ph, ph_feedback))
        self.__ph.value = ph_feedback
        self._proxy.wait()

    def on_enter_running_waiting(self):
        logger.info("Entering waiting state")
        self._proxy.do_delay(10, "measure")
