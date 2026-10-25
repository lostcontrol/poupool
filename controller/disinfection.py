# Poupool - swimming pool control software
# Copyright (C) 2019 Cyril Jaquier
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import logging
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Final, NamedTuple

from .actor import PoupoolActor, PoupoolModel
from .config import config
from .util import Timer, constrain

logger = logging.getLogger(__name__)


class PWM(PoupoolActor):
    SECURITY_DURATION = int(config["disinfection", "security_duration"])

    def __init__(self, name, pump, period=120, min_runtime=3):
        super().__init__()
        self.__name = name
        self.__pump = pump
        self.period = period
        self.__last = None
        self.__duration = 0
        self.__state = False
        self.__security_duration = Timer(f"PWM for {name}")
        self.__security_duration.delay = timedelta(hours=PWM.SECURITY_DURATION)
        self.__security_reset = datetime.now() + timedelta(days=1)
        self.__min_runtime = min_runtime
        self.value = 0.0

    def do_cancel(self):
        super().do_cancel()
        # Clear the security duration counter and last time during a pause
        self.__security_duration.clear()
        self.__last = None
        self.__pump.off()

    def do_run(self):
        now = time.time()
        if self.__last is not None:
            diff = now - self.__last
            self.__duration += diff
            self.__duration = constrain(self.__duration, 0, self.period)
            duty_on = self.value * self.period
            # Avoid short commutations. If below min_runtime but higher than zero we run at
            # min_runtime. If higher than period - min_runtime, we run at period (max)
            if duty_on != 0 and duty_on < self.__min_runtime:
                duty_on = self.__min_runtime
            elif duty_on > self.period - self.__min_runtime:
                duty_on = self.period
            duty_off = self.period - duty_on
            if int(now) % 10 == 0:
                logger.debug(
                    f"{self.__name} duty (on/off): {duty_on:.1f}/{duty_off:.1f} "
                    "state: {self.__state} duration: {self.__duration:.1f}"
                )
            if self.__state:
                self.__security_duration.update(datetime.now())
                if self.__duration >= duty_on and duty_on != self.period:
                    self.__duration = 0
                    self.__state = False
                    self.__pump.off()
            else:
                self.__security_duration.update(datetime.now(), 0)
                security_ok = not self.__security_duration.elapsed()
                if self.__duration >= duty_off and duty_off != self.period and security_ok:
                    self.__duration = 0
                    self.__state = True
                    self.__pump.on()
        if datetime.now() > self.__security_reset:
            self.__security_duration.reset()
            self.__security_reset += timedelta(days=1)
        self.__last = now
        self.do_delay(1, self.do_run.__name__)


class PController:
    def __init__(self, pterm=0.1, scale=1.0):
        self.setpoint = 0
        self.current = 0
        self.pterm = pterm
        self.__scale = scale

    def compute(self):
        error = self.setpoint - self.current
        return constrain((self.pterm * self.__scale) * error, 0, 1)


class CycleStats(NamedTuple):
    peak: float
    mean: float


class CanisterMonitor:
    MIN_CYCLE_SAMPLES: Final = 15
    MAX_CYCLE_SAMPLES: Final = 120

    def __init__(
        self,
        name: str,
        cycles: int = 6,
        min_samples: int = MIN_CYCLE_SAMPLES,
        max_samples: int = MAX_CYCLE_SAMPLES,
    ) -> None:
        self.__name: str = name
        self.__cycles_count: int = cycles
        self.__min_samples: int = min_samples
        self.__max_samples: int = max_samples
        self.__history: deque[CycleStats] = deque(maxlen=cycles)
        self.__current_samples: list[float] = []
        self.__is_empty: bool = False
        self.__alert_stats: CycleStats | None = None

    @property
    def is_empty(self) -> bool:
        return self.__is_empty

    @property
    def history(self) -> list[CycleStats]:
        return list(self.__history)

    @property
    def current_samples(self) -> list[float]:
        return list(self.__current_samples)

    @property
    def alert_stats(self) -> CycleStats | None:
        return self.__alert_stats

    def restore(self, is_empty: bool) -> None:
        self.__is_empty = is_empty
        if not is_empty:
            self.__alert_stats = None
            self.__history.clear()
            self.__current_samples.clear()

    def add_sample(self, value: float) -> bool:
        """Record a sample. Returns True if is_empty state changed."""
        self.__current_samples.append(value)
        if self.__is_empty and len(self.__current_samples) >= self.__min_samples:
            current = self.__compute_current_stats()
            if self.__is_low_demand(current):
                logger.info(f"{self.__name} canister refilled: low duty cycle restored ({current.peak * 100:.1f}%)")
                self.__clear_empty()
                return True
        if len(self.__current_samples) >= self.__max_samples:
            return self.finish_cycle()
        return False

    def finish_cycle(self) -> bool:
        """Finalize the current cycle. Returns True if is_empty state changed."""
        if len(self.__current_samples) < self.__min_samples:
            self.__current_samples.clear()
            return False
        stats = self.__compute_current_stats()
        self.__current_samples.clear()
        if self.__is_empty:
            if self.__should_clear(stats):
                logger.info(
                    f"{self.__name} canister refilled: duty cycle dropped "
                    f"(peak: {stats.peak * 100:.1f}%, mean: {stats.mean * 100:.1f}%)"
                )
                self.__clear_empty()
                return True
            if self.__alert_stats is None or stats.peak > self.__alert_stats.peak:
                self.__alert_stats = stats
            return False
        self.__history.append(stats)
        if self.__should_trigger():
            self.__is_empty = True
            self.__alert_stats = stats
            logger.warning(
                f"{self.__name} canister empty detected! Peak: {stats.peak * 100:.1f}%, mean: {stats.mean * 100:.1f}%"
            )
            return True
        return False

    def __compute_current_stats(self) -> CycleStats:
        return CycleStats(
            peak=max(self.__current_samples),
            mean=sum(self.__current_samples) / len(self.__current_samples),
        )

    def __should_trigger(self) -> bool:
        if len(self.__history) < self.__cycles_count:
            return False
        peaks = [c.peak for c in self.__history]
        means = [c.mean for c in self.__history]

        # All cycles in the window must show persistent demand (never recovering to low duty cycle)
        if any(p < 0.08 or m < 0.06 for p, m in zip(peaks, means, strict=True)):
            return False

        # 1. High-duty saturation fallback (all cycles sustained high)
        if all(p >= 0.35 and m >= 0.25 for p, m in zip(peaks, means, strict=True)):
            return True

        # 2. Consistent multi-cycle upward trend in peak or mean
        if peaks[-1] < 0.20 and means[-1] < 0.15:
            return False
        return self.__has_upward_trend(peaks, min_delta=0.12) or self.__has_upward_trend(means, min_delta=0.10)

    @staticmethod
    def __has_upward_trend(values: list[float], min_delta: float, tolerance: float = 0.01) -> bool:
        n = len(values)
        if values[-1] - values[0] < min_delta:
            return False
        increasing = sum(1 for i in range(1, n) if values[i] > values[i - 1])
        no_drops = all(values[i] >= values[i - 1] - tolerance for i in range(1, n))
        return increasing >= n - 2 and no_drops

    @staticmethod
    def __is_low_demand(stats: CycleStats) -> bool:
        return stats.peak < 0.10 and stats.mean < 0.08

    def __should_clear(self, stats: CycleStats) -> bool:
        if self.__is_low_demand(stats):
            return True
        return (
            self.__alert_stats is not None
            and stats.peak <= self.__alert_stats.peak - 0.15
            and stats.mean <= self.__alert_stats.mean * 0.5
        )

    def __clear_empty(self) -> None:
        self.__is_empty = False
        self.__alert_stats = None
        self.__history.clear()


class Disinfection(PoupoolActor):
    STATE_REFRESH_DELAY = 10
    START_DELAY = int(config["disinfection", "start_delay"])
    WAITING_DELAY = int(config["disinfection", "waiting_delay"])
    PH_PWM_PERIOD = int(config["disinfection", "ph_pwm_period"])
    CL_PWM_PERIOD = int(config["disinfection", "cl_pwm_period"])
    CANISTER_CYCLES = int(config["disinfection", "canister_cycles"])

    states: Final = [
        "halt",
        "waiting",
        {"name": "running", "initial": "adjusting", "children": ["adjusting", "treating"]},
    ]

    def __init__(self, encoder, devices, sensors_reader, sensors_writer, disable=False):
        super().__init__()
        self.__is_disabled = disable
        self.__encoder = encoder
        self.__devices = devices
        self.__sensors_reader = sensors_reader
        self.__sensors_writer = sensors_writer
        # pH
        self.__ph_enable = True
        self.__ph = PWM.start("pH", self.__devices.get_pump("ph")).proxy()
        self.__ph.period = Disinfection.PH_PWM_PERIOD
        self.__ph_controller = PController(pterm=-1.0)
        self.__ph_controller.setpoint = 7
        # ORP
        self.__orp_enable = True
        self.__orp_controller = PController(pterm=1.0, scale=0.005)
        self.__orp_controller.setpoint = 600
        # Chlorine
        self.__cl = PWM.start("cl", self.__devices.get_pump("cl")).proxy()
        self.__cl.period = Disinfection.CL_PWM_PERIOD
        # Canister empty monitors
        self.__ph_canister = CanisterMonitor("pH", cycles=Disinfection.CANISTER_CYCLES)
        self.__cl_canister = CanisterMonitor("Cl", cycles=Disinfection.CANISTER_CYCLES)
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Disinfection.states, initial="halt")

        self.__machine.add_transition("run", "halt", "waiting", unless="is_disabled")
        self.__machine.add_transition("run", "waiting", "running")
        self.__machine.add_transition("halt", ["waiting", "running"], "halt")
        self.__machine.add_transition("adjust", "running_treating", "running_adjusting")
        self.__machine.add_transition("treat", "running_adjusting", "running_treating")

    def ph_enable(self, value):
        self.__ph_enable = value
        logger.info("pH adjustment is %sabled" % ("en" if value else "dis"))

    def orp_enable(self, value):
        self.__orp_enable = value
        logger.info("ORP adjustment is %sabled" % ("en" if value else "dis"))

    def ph_setpoint(self, value):
        self.__ph_controller.setpoint = value
        logger.info(f"pH setpoint set to: {self.__ph_controller.setpoint:.2f}")

    def orp_setpoint(self, value):
        self.__orp_controller.setpoint = value
        logger.info(f"ORP setpoint set to: {self.__orp_controller.setpoint}")

    def ph_pterm(self, value):
        # We assume here that we use "pH minus" chemicals, therefore inverse the term.
        self.__ph_controller.pterm = -value
        logger.info(f"pH pterm set to: {self.__ph_controller.pterm:.2f}")

    def orp_pterm(self, value):
        self.__orp_controller.pterm = value
        logger.info(f"ORP pterm set to: {self.__orp_controller.pterm:.2f}")

    def ph_canister_empty(self, value: bool) -> None:
        if self.__ph_canister.is_empty != value:
            self.__ph_canister.restore(value)
            logger.info(f"pH canister empty flag set to {value}")

    def cl_canister_empty(self, value: bool) -> None:
        if self.__cl_canister.is_empty != value:
            self.__cl_canister.restore(value)
            logger.info(f"Cl canister empty flag set to {value}")

    @property
    def ph_canister(self) -> CanisterMonitor:
        return self.__ph_canister

    @property
    def cl_canister(self) -> CanisterMonitor:
        return self.__cl_canister

    def is_disabled(self):
        return self.__is_disabled

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.__encoder.disinfection_state("halt")
        self.__ph.value = 0
        self.__cl.value = 0
        self.__ph.do_cancel.defer()
        self.__cl.do_cancel.defer()
        self.__encoder.disinfection_cl_feedback(0)
        self.__encoder.disinfection_ph_feedback(0)
        self.__sensors_writer.do_cancel.defer()
        if self.__ph_enable and self.__ph_canister.finish_cycle():
            self.__encoder.disinfection_ph_canister__empty(1 if self.__ph_canister.is_empty else 0, retain=True)
        if self.__orp_enable and self.__cl_canister.finish_cycle():
            self.__encoder.disinfection_cl_canister__empty(1 if self.__cl_canister.is_empty else 0, retain=True)

    def on_enter_waiting(self):
        logger.info("Entering waiting state")
        self.__encoder.disinfection_state("waiting")
        self.do_delay(Disinfection.START_DELAY, "run")

    def on_enter_running(self):
        logger.info("Entering running state")
        self.__ph.do_run.defer()
        self.__cl.period = Disinfection.CL_PWM_PERIOD
        self.__cl.do_run.defer()
        self.__sensors_writer.do_write.defer()

    def on_enter_running_adjusting(self):
        logger.debug("Entering adjusting state")
        self.__encoder.disinfection_state("adjusting")
        # pH
        ph = self.__sensors_reader.get_ph().get()
        self.__ph_controller.current = ph
        ph_feedback = self.__ph_controller.compute() if self.__ph_enable else 0
        self.__encoder.disinfection_ph_feedback(round(ph_feedback * 100))
        logger.debug(f"pH: {ph:.2f} feedback: {ph_feedback:.2f}")
        self.__ph.value = ph_feedback
        if self.__ph_enable and self.__ph_canister.add_sample(ph_feedback):
            self.__encoder.disinfection_ph_canister__empty(1 if self.__ph_canister.is_empty else 0, retain=True)
        # ORP/Chlorine
        orp = self.__sensors_reader.get_orp().get()
        self.__orp_controller.current = orp
        cl_feedback = self.__orp_controller.compute() if self.__orp_enable else 0
        self.__encoder.disinfection_cl_feedback(round(cl_feedback * 100))
        logger.debug(f"ORP: {orp} feedback: {cl_feedback:.2f}")
        self.__cl.value = cl_feedback
        if self.__orp_enable and self.__cl_canister.add_sample(cl_feedback):
            self.__encoder.disinfection_cl_canister__empty(1 if self.__cl_canister.is_empty else 0, retain=True)
        self._proxy.treat.defer()

    def on_enter_running_treating(self):
        logger.debug("Entering treating state")
        self.__encoder.disinfection_state("treating")
        self.do_delay(Disinfection.WAITING_DELAY, "adjust")
