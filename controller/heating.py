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

import pykka
import time
import logging
from datetime import datetime, timedelta
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import StopRepeatException, repeat, do_repeat
from .util import Timer
from .config import config

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

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_waiting(self):
        temp = self.__read_temperature()
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
        temp = self.__read_temperature()
        if temp > self.__setpoint + Heater.HYSTERESIS_UP:
            self._proxy.wait()
            raise StopRepeatException


class Heating(PoupoolActor):

    STATE_REFRESH_DELAY = 10
    HYSTERESIS_DOWN = float(config["heating", "hysteresis_down"])
    HYSTERESIS_UP = float(config["heating", "hysteresis_up"])
    RECOVER_PERIOD = int(config["heating", "recover_period"])

    states = ["halt", "waiting", "heating", "forcing", "recovering"]

    def __init__(self, temperature, encoder, devices):
        super().__init__()
        self.__enable = True
        self.__temperature = temperature
        self.__encoder = encoder
        self.__devices = devices
        self.__next_start = datetime.now()
        self.__setpoint = 26.0
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

    def __read_temperature(self):
        return self.__temperature.get_temperature("temperature_pool").get()

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
        tm = datetime.now()
        self.__next_start = tm.replace(hour=value, minute=0, second=0, microsecond=0)
        if self.__next_start < tm:
            self.__next_start -= timedelta(days=1)

    def filtration_ready_for_heating(self):
        actor = self.get_actor("Filtration")
        return actor.is_eco_waiting().get() or actor.is_eco_normal().get()

    def filtration_allow_heating(self):
        actor = self.get_actor("Filtration")
        return actor.is_heating_running().get()

    def check_before_on(self):
        temperature = self.__read_temperature()
        return (temperature - Heating.HYSTERESIS_DOWN) < self.__setpoint

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.__encoder.heating_state("halt")
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
            if self.__enable and self.filtration_ready_for_heating():
                if self.check_before_on():
                    self.get_actor("Filtration").heat()
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
        temperature = self.__read_temperature()
        if temperature >= self.__setpoint + Heating.HYSTERESIS_UP or not self.__enable:
            self.__next_start += timedelta(days=1)
            self._proxy.wait()
            raise StopRepeatException

    def on_exit_heating(self):
        logger.info("Exiting heating state")
        self.__devices.get_valve("heating").off()
        # Only change the filtration state if we are running in heating_running state
        if self.filtration_allow_heating():
            self.get_actor("Filtration").heating_delay()

    def on_enter_forcing(self):
        logger.info("Entering forcing state")
        self.__encoder.heating_state("heating")
        self.__devices.get_valve("heating").on()

    def on_exit_forcing(self):
        logger.info("Exiting forcing state")
        self.__devices.get_valve("heating").off()

    def on_enter_recovering(self):
        logger.info("Entering recovering state")
        self.__encoder.heating_state("recovering")
        self.do_delay(Heating.RECOVER_PERIOD, "recover_done")
