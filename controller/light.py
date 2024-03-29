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
from typing import Final

# from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor, PoupoolModel

logger = logging.getLogger(__name__)


class Light(PoupoolActor):
    STATE_REFRESH_DELAY = 10

    states: Final = ["halt", "on"]

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__devices = devices
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Light.states, initial="halt")

        self.__machine.add_transition("on", "halt", "on")
        self.__machine.add_transition("halt", "on", "halt")

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.__encoder.light_state("halt")
        self.__devices.get_valve("light").off()

    def on_enter_on(self):
        logger.info("Entering on state")
        self.__encoder.light_state("on")
        self.__devices.get_valve("light").on()
