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
from datetime import datetime, timedelta
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import do_repeat
from .config import config
from .util import Duration

logger = logging.getLogger(__name__)


class Heater(PoupoolActor):

    STATE_REFRESH_DELAY = 10
    HYSTERESIS_DOWN = float(config["heater", "hysteresis_down"])
    HYSTERESIS_UP = float(config["heater", "hysteresis_up"])

    states = ["halt", "waiting", "heating"]

    def __init__(self, temperature, heater):
        super().__init__()
        self.__temperature = temperature
        self.__heater = heater
        self.__setpoint = 5.0
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Heating.states, initial="halt")

        self.__machine.add_transition(
            "wait", ["halt", "heating"], "waiting", conditions="has_heater")
        self.__machine.add_transition("heat", "waiting", "heating")
        self.__machine.add_transition("halt", ["waiting", "heating"], "halt")

    def __read_temperature(self):
        return self.__temperature.get_temperature("temperature_local").get()

    def has_heater(self):
        return self.__heater is not None

    def setpoint(self, value):
        self.__setpoint = value
        logger.info("Setpoint set to %.1f" % self.__setpoint)

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.__heater.off()

    @do_repeat()
    def on_enter_waiting(self):
        logger.info("Entering waiting state")

    def do_repeat_waiting(self):
        temp = self.__read_temperature()
        if temp is None or temp < self.__setpoint - Heater.HYSTERESIS_DOWN:
            self._proxy.heat.defer()
        else:
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_waiting.__name__)

    @do_repeat()
    def on_enter_heating(self):
        logger.info("Entering heating state")
        self.__heater.on()

    def on_exit_heating(self):
        self.__heater.off()

    def do_repeat_heating(self):
        temp = self.__read_temperature()
        if temp is not None and temp > self.__setpoint + Heater.HYSTERESIS_UP:
            self._proxy.wait.defer()
        else:
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_heating.__name__)


class Heating(PoupoolActor):

    STATE_REFRESH_DELAY = 10
    HYSTERESIS_DOWN = float(config["heating", "hysteresis_down"])
    HYSTERESIS_UP = float(config["heating", "hysteresis_up"])
    HYSTERESIS_MIN_TEMP = float(config["heating", "hysteresis_min_temp"])
    RECOVER_PERIOD = int(config["heating", "recover_period"])

    states = ["halt", "waiting", "heating", "forcing", "recovering"]

    class DurationEncoderCallback(object):

        def __init__(self, encoder):
            self.__encoder = encoder

        def __call__(self, value):
            self.__encoder.heating_total__seconds(round(value.total_seconds()), retain=True)

    def __init__(self, temperature, encoder, devices):
        super().__init__()
        self.__enable = True
        self.__temperature = temperature
        self.__encoder = encoder
        self.__total_duration = Duration("heating")
        self.__total_duration.set_callback(Heating.DurationEncoderCallback(encoder))
        self.__devices = devices
        self.__next_start = datetime.now()
        self.__next_start_hour = 0
        self.__setpoint = 26.0
        self.__min_temp = 15
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Heating.states, initial="halt")

        self.__machine.add_transition("wait", "halt", "waiting")
        self.__machine.add_transition("heat", ["halt", "waiting"], "heating",
                                      conditions="filtration_allow_heating")
        self.__machine.add_transition("force", ["halt", "waiting"], "forcing")
        self.__machine.add_transition(
            "halt", ["waiting", "heating", "forcing", "recovering"], "halt")
        self.__machine.add_transition("wait", ["heating", "forcing"], "recovering")
        self.__machine.add_transition("recover_done", "recovering", "waiting")

    def __read_temperature(self, key="temperature_pool"):
        return self.__temperature.get_temperature(key).get()

    def __set_next_start(self):
        tm = datetime.now()
        self.__next_start = tm.replace(hour=self.__next_start_hour,
                                       minute=0, second=0, microsecond=0)
        self.__next_start += timedelta(days=1)

    def total_seconds(self, value):
        duration = timedelta(seconds=value)
        self.__total_duration.init(duration)
        logger.info("Total running hours set to %s" % duration)

    def enable(self, value):
        self.__enable = value
        logger.info("Heating is %sabled" % ("en" if value else "dis"))

    def setpoint(self, value):
        self.__setpoint = value
        logger.info("Setpoint set to %.1f" % self.__setpoint)
        # Hack. Restart the heating if the setpoint is changed
        if self.__next_start > datetime.now():
            self.__next_start -= timedelta(days=1)

    def start_hour(self, value):
        logger.info("Hour for heating start set to: %s" % value)
        self.__next_start_hour = value
        self.__set_next_start()
        if self.__next_start < datetime.now():
            self.__next_start -= timedelta(days=1)
        logger.info("Next heating scheduled for %s" % self.__next_start)

    def min_temp(self, value):
        self.__min_temp = value
        logger.info("Minimum temperature for heating set to %d" % self.__min_temp)

    def filtration_ready_for_heating(self):
        actor = self.get_actor("Filtration")
        return actor.is_eco_waiting().get() or actor.is_eco_normal().get()

    def filtration_allow_heating(self):
        actor = self.get_actor("Filtration")
        return actor.is_heating_running().get()

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.__encoder.heating_state("halt")
        self.__devices.get_valve("heating").off()

    @do_repeat()
    def on_enter_waiting(self):
        logger.info("Entering waiting state")
        self.__devices.get_valve("heating").off()
        self.__encoder.heating_state("waiting")

    def do_repeat_waiting(self):
        if not self.__enable:
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_waiting.__name__)
            return
        # First, we check if the daily run is due
        if datetime.now() < self.__next_start:
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_waiting.__name__)
            return
        # After the time constrain is fulfilled, we check if the temperature is low enough to
        # require heating. If not, then we say it's all good for today and schedule another heating
        # check for tomorrow.
        temp = self.__read_temperature()
        if temp is not None and (temp - Heating.HYSTERESIS_DOWN) >= self.__setpoint:
            # No need to heat today. Schedule for next day
            self.__set_next_start()
            logger.info("No heating needed today. Scheduled for %s" % self.__next_start)
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_waiting.__name__)
            return
        # We ensure the outside temperature is high enough to get a good efficiency from the
        # heat pump
        temp = self.__read_temperature("temperature_air")
        if temp is not None and temp < self.__min_temp:
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_waiting.__name__)
            return
        # Finally we check that filtration is ready to be switched to heating
        if not self.filtration_ready_for_heating():
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_waiting.__name__)
            return
        # All pre-conditions ok, we can start heating now
        self.get_actor("Filtration").heat().get()
        # Ensure we are allowed to switch to the heat state. If the transition above fails,
        # we will call StopRepeatException but never land in the heating state.
        if self.filtration_allow_heating():
            self._proxy.heat.defer()
        else:
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_waiting.__name__)

    @do_repeat()
    def on_enter_heating(self):
        logger.info("Entering heating state")
        self.__total_duration.start()
        self.__encoder.heating_state("heating")
        self.__devices.get_valve("heating").on()

    def do_repeat_heating(self):
        if not self.__enable:
            self._proxy.wait.defer()
            return
        temperature_pool = self.__read_temperature()
        if temperature_pool is None or temperature_pool >= self.__setpoint + Heating.HYSTERESIS_UP:
            self._proxy.wait.defer()
            return
        # If the air temperature goes too low, we stop the heat pump otherwise the efficiency
        # will be too bad.
        temperature_air = self.__read_temperature("temperature_air")
        if temperature_air is not None and temperature_air < self.__min_temp - Heating.HYSTERESIS_MIN_TEMP:
            self._proxy.wait.defer()
            return
        self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_heating.__name__)

    def on_exit_heating(self):
        logger.info("Exiting heating state")
        self.__total_duration.stop()
        self.__devices.get_valve("heating").off()
        # If the heating is aborted by the user, we also consider it as done and will heat again
        # the next day. If the heating ends normally then we are anyway done for the day.
        self.__set_next_start()
        logger.info("Heating done for today. Scheduled for %s" % self.__next_start)
        # Only change the filtration state if we are running in heating_running state
        if self.filtration_allow_heating():
            self.get_actor("Filtration").heating_delay.defer()

    def on_enter_forcing(self):
        logger.info("Entering forcing state")
        self.__total_duration.start()
        self.__encoder.heating_state("heating")
        self.__devices.get_valve("heating").on()

    def on_exit_forcing(self):
        logger.info("Exiting forcing state")
        self.__total_duration.stop()
        self.__devices.get_valve("heating").off()

    def on_enter_recovering(self):
        logger.info("Entering recovering state")
        self.__encoder.heating_state("recovering")
        self.do_delay(Heating.RECOVER_PERIOD, "recover_done")
