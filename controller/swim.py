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
# from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import do_repeat
from .util import Timer
from .config import config

logger = logging.getLogger(__name__)


class Swim(PoupoolActor):

    STATE_REFRESH_DELAY = 1  # faster refresh rate because speed can change
    WINTERING_PERIOD = int(config["wintering", "swim_period"])
    WINTERING_ONLY_BELOW = float(config["wintering", "swim_only_below"])
    WINTERING_DURATION = int(config["wintering", "swim_duration"])

    states = ["halt",
              "timed",
              "continuous",
              {"name": "wintering", "initial": "waiting", "children": [
                  "stir",
                  "waiting"]}]

    def __init__(self, temperature, encoder, devices):
        super().__init__()
        self.__temperature = temperature
        self.__encoder = encoder
        self.__devices = devices
        self.__timer = Timer("swim")
        self.__speed = 50
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Swim.states, initial="halt")

        self.__machine.add_transition("timed", "halt", "timed", conditions="filtration_allow_swim")
        self.__machine.add_transition("wintering", "halt", "wintering",
                                      conditions="filtration_is_wintering")
        self.__machine.add_transition("wintering_stir", "wintering_waiting", "wintering_stir")
        self.__machine.add_transition("wintering_waiting", "wintering_stir", "wintering_waiting")
        self.__machine.add_transition("timed", "continuous", "timed",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("continuous", "halt", "continuous",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("continuous", "timed", "continuous",
                                      conditions="filtration_allow_swim")
        self.__machine.add_transition("halt", ["timed", "continuous", "wintering"], "halt")

    def timer(self, value):
        self.__timer.delay = timedelta(minutes=value)
        logger.info("Timer for swim set to: %s" % self.__timer.delay)

    def speed(self, value):
        self.__speed = value
        logger.info("Speed for swim pump set to: %d" % self.__speed)

    def filtration_allow_swim(self):
        actor = self.get_actor("Filtration")
        is_opened = actor.is_overflow_normal().get() or actor.is_standby_normal().get()
        is_opened = is_opened or actor.is_comfort().get()
        return is_opened or self.filtration_is_wintering()

    def filtration_is_wintering(self):
        actor = self.get_actor("Filtration")
        return actor.is_wintering_waiting().get() or actor.is_wintering_stir().get()

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.__encoder.swim_state("halt")
        self.__devices.get_pump("swim").off()

    @do_repeat()
    def on_enter_timed(self):
        logger.info("Entering timed state")
        self.__encoder.swim_state("timed")
        self.__timer.reset()

    def do_repeat_timed(self):
        self.__devices.get_pump("swim").speed(self.__speed)
        self.__timer.update(datetime.now())
        if self.__timer.elapsed():
            self._proxy.halt.defer()
        else:
            self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_timed.__name__)

    @do_repeat()
    def on_enter_continuous(self):
        logger.info("Entering continuous state")
        self.__encoder.swim_state("continuous")

    def do_repeat_continuous(self):
        self.__devices.get_pump("swim").speed(self.__speed)
        self.do_delay(self.STATE_REFRESH_DELAY, self.do_repeat_continuous.__name__)

    @do_repeat()
    def on_enter_wintering_waiting(self):
        logger.info("Entering wintering waiting state")
        self.__encoder.swim_state("wintering_waiting")
        self.__devices.get_pump("swim").off()

    def do_repeat_wintering_waiting(self):
        if self.__machine.get_time_in_state() > timedelta(seconds=Swim.WINTERING_PERIOD):
            temperature = self.__temperature.get_temperature("temperature_ncc").get()
            if temperature is None or temperature <= Swim.WINTERING_ONLY_BELOW:
                self._proxy.wintering_stir.defer()
                return
        self.do_delay(2 * 60, self.do_repeat_wintering_waiting.__name__)

    def on_enter_wintering_stir(self):
        logger.info("Entering wintering stir state")
        self.__encoder.swim_state("wintering_stir")
        self.__devices.get_pump("swim").on()
        self.do_delay(Swim.WINTERING_DURATION, "wintering_waiting")
