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
import datetime
# from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import StopRepeatException, do_repeat
from .config import config

logger = logging.getLogger(__name__)


class Tank(PoupoolActor):

    STATE_REFRESH_DELAY = 10

    states = ["halt", "fill", "low", "normal", "high"]

    hysteresis = int(config["tank", "hysteresis"])
    levels_too_low = int(config["tank", "too_low"])
    levels_eco = {
        "low": int(config["tank", "eco_low"]),
        "high": int(config["tank", "eco_high"]),
    }
    levels_overflow = {
        "low": int(config["tank", "overflow_low"]),
        "high": int(config["tank", "overflow_high"]),
    }

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__devices = devices
        self.__force_empty = False
        self.levels = self.levels_eco
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Tank.states, initial="halt")

        self.__machine.add_transition("low", ["fill", "normal"], "low")
        self.__machine.add_transition("normal", ["fill", "low", "high"], "normal")
        self.__machine.add_transition("high", ["fill", "normal"], "high")
        self.__machine.add_transition("halt", ["fill", "low", "normal", "high"], "halt")
        self.__machine.add_transition("fill", "halt", "fill", unless="is_force_empty")

    def __get_tank_height(self):
        height = self.__devices.get_sensor("tank").value
        logger.debug("Tank level: %d" % height)
        self.__encoder.tank_height(int(round(height)))
        return height

    def force_empty(self, value):
        previous = self.__force_empty
        self.__force_empty = value
        logger.info("Force empty tank is %sabled" % ("en" if value else "dis"))
        if not previous and self.__force_empty and not self.is_halt():
            # In case the user enable the settings and we are running already, we stop everything.
            # The user can continue from the halt state.
            logger.warning("The tank is not in the halt state, stopping everything")
            self.get_actor("Filtration").halt.defer()
        elif previous and not self.__force_empty and self.is_halt():
            # Deactivation of the function, we start the tank FSM.
            self._proxy.fill.defer()

    def is_force_empty(self):
        return self.__force_empty

    def set_mode(self, mode):
        logger.info("Tank level set to %s" % mode)
        self.levels = self.levels_eco if mode == "eco" else self.levels_overflow

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.__encoder.tank_state("halt")
        self.__devices.get_valve("main").off()

    @do_repeat()
    def on_enter_fill(self):
        logger.info("Entering fill state")
        self.__encoder.tank_state("fill")
        height = self.__get_tank_height()
        if height < self.levels_too_low:
            self.__devices.get_valve("main").on()
        else:
            self._proxy.normal.defer()
            raise StopRepeatException

    def do_repeat_fill(self):
        # Security feature: stop if we stay too long in this state
        if self.__machine.get_time_in_state() > datetime.timedelta(hours=2):
            logger.warning("Tank TOO LONG in fill state, stopping")
            self.get_actor("Filtration").halt.defer()
            return
        height = self.__get_tank_height()
        if height > self.levels_too_low:
            self._proxy.low.defer()
            return
        self.do_delay(self.STATE_REFRESH_DELAY / 2, self.do_repeat_fill.__name__)

    @do_repeat()
    def on_enter_low(self):
        logger.info("Entering low state")
        self.__encoder.tank_state("low")
        self.__devices.get_valve("main").on()

    def do_repeat_low(self):
        # Security feature: stop if we stay too long in this state
        if self.__machine.get_time_in_state() > datetime.timedelta(hours=6):
            logger.warning("Tank TOO LONG in low state, stopping")
            self.get_actor("Filtration").halt.defer()
            return
        height = self.__get_tank_height()
        if height >= self.levels["low"] + self.hysteresis:
            self._proxy.normal.defer()
            return
        elif height < self.levels_too_low:
            logger.warning("Tank TOO LOW, stopping: %d" % height)
            self.get_actor("Filtration").halt.defer()
            return
        self.do_delay(self.STATE_REFRESH_DELAY / 2, self.do_repeat_low.__name__)

    @do_repeat()
    def on_enter_normal(self):
        logger.info("Entering normal state")
        self.__encoder.tank_state("normal")
        self.__devices.get_valve("main").off()

    def do_repeat_normal(self):
        height = self.__get_tank_height()
        if height < self.levels["low"] - self.hysteresis:
            self._proxy.low.defer()
            return
        elif height >= self.levels["high"] + self.hysteresis:
            self._proxy.high.defer()
            return
        self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_normal.__name__)

    @do_repeat()
    def on_enter_high(self):
        logger.info("Entering high state")
        self.__encoder.tank_state("high")
        self.__devices.get_valve("main").off()

    def do_repeat_high(self):
        height = self.__get_tank_height()
        if height < self.levels["high"] - self.hysteresis:
            self._proxy.normal.defer()
        else:
            self.do_delay(self.STATE_REFRESH_DELAY * 2, self.do_repeat_high.__name__)
