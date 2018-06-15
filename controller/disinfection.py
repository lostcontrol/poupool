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

    def __init__(self, name, pump, period=120):
        super().__init__()
        self.__name = name
        self.__pump = pump
        self.__period = period
        self.__last = None
        self.__duration = 0
        self.__state = False
        self.__security_duration = Timer("PWM for %s" % name)
        self.__security_duration.delay = timedelta(hours=2)
        self.__security_reset = datetime.now() + timedelta(days=1)
        self.value = 0.0

    @repeat(delay=4)
    def do_run(self):
        now = time.time()
        if self.__last:
            diff = now - self.__last
            self.__duration += diff
            self.__duration = constrain(self.__duration, 0, self.__period)
            duty_on = self.value * self.__period
            duty_off = self.__period - duty_on
            duty = duty_on if self.__state else duty_off
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

    def __init__(self, pterm=0.1, scale=1.0):
        self.setpoint = 0
        self.current = 0
        self.pterm = pterm
        self.__scale = scale

    def compute(self):
        error = self.setpoint - self.current
        return constrain((self.pterm * self.__scale) * error, 0, 1)


class Disinfection(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    curves = {
        "low": lambda x: -45.162 * x + 1002,         # 0.8
        "mid": lambda x: -50 * x + 1065,             # 1.0
        "mid_high": lambda x: -55.691 * x + 1138.9,  # 1.3
        "high": lambda x: -58.618 * x + 1178.1,      # 1.5
    }

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
        # pH
        self.__ph_measures = []
        self.__ph = PWM.start("pH", self.__devices.get_pump("ph")).proxy()
        self.__ph_controller = PController(pterm=-1.0)
        self.__ph_controller.setpoint = 7
        # ORP
        self.__orp_measures = []
        self.__orp_controller = PController(pterm=1.0, scale=0.01)
        self.__orp_controller.setpoint = 700
        # Chlorine
        self.__cl = PWM.start("cl", self.__devices.get_pump("cl")).proxy()
        self.__free_chlorine = "low"
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

    def free_chlorine(self, value):
        if value in self.curves:
            self.__free_chlorine = value
            logger.info("Free chlorine level set to: %s" % self.__free_chlorine)
        else:
            logger.error("Unsupported free chlorine level: %s" % value)

    def ph_pterm(self, value):
        # We assume here that we use "pH minus" chemicals, therefore inverse the term.
        self.__ph_controller.pterm = -value
        logger.info("pH pterm set to: %f" % self.__ph_controller.pterm)

    def orp_pterm(self, value):
        self.__orp_controller.pterm = value
        logger.info("ORP pterm set to: %f" % self.__orp_controller.pterm)

    def is_disable(self):
        return self.__is_disable

    def on_enter_stop(self):
        logger.info("Entering stop state")
        self.__encoder.disinfection_state("stop")

    def on_enter_waiting(self):
        logger.info("Entering waiting state")
        self.__encoder.disinfection_state("waiting")
        self._proxy.do_delay(300, "run")

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
        self.__orp_measures = []

    @repeat(delay=30)
    def do_repeat_running_measuring(self):
        self.__ph_measures.append(self.__devices.get_sensor("ph").value)
        self.__orp_measures.append(self.__devices.get_sensor("orp").value)
        if len(self.__ph_measures) > 3:
            self._proxy.adjust()
            raise StopRepeatException

    def on_enter_running_adjusting(self):
        logger.info("Entering adjusting state")
        self.__encoder.disinfection_state("adjusting")
        # pH
        ph = sum(self.__ph_measures) / len(self.__ph_measures)
        self.__encoder.disinfection_ph_value("%.2f" % ph)
        self.__ph_controller.current = ph
        ph_feedback = self.__ph_controller.compute()
        self.__encoder.disinfection_ph_feedback(int(round(ph_feedback * 100)))
        logger.info("pH: %.2f feedback: %.2f" % (ph, ph_feedback))
        self.__ph.value = ph_feedback
        # ORP/Chlorine
        orp = sum(self.__orp_measures) / len(self.__orp_measures)
        self.__encoder.disinfection_orp_value("%d" % orp)
        orp_setpoint = self.curves[self.__free_chlorine](ph)
        self.__orp_controller.setpoint = orp_setpoint
        self.__orp_controller.current = orp
        cl_feedback = self.__orp_controller.compute()
        self.__encoder.disinfection_cl_feedback(int(round(cl_feedback * 100)))
        self.__encoder.disinfection_orp_setpoint(int(orp_setpoint))
        logger.info("ORP: %d setpoint: %d feedback: %.2f" % (orp, orp_setpoint, cl_feedback))
        self.__cl.value = cl_feedback
        self._proxy.wait()

    def on_enter_running_waiting(self):
        logger.info("Entering waiting state")
        self.__encoder.disinfection_state("treating")
        self._proxy.do_delay(4 * 60, "measure")
