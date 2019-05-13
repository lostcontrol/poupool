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
import datetime
#from transitions.extensions import GraphMachine as Machine
from .actor import PoupoolActor
from .actor import PoupoolModel
from .actor import StopRepeatException, repeat, do_repeat
from .util import Timer

logger = logging.getLogger(__name__)


class Arduino(PoupoolActor):

    STATE_REFRESH_DELAY = 60

    states = ["halt", "run"]

    def __init__(self, encoder, devices):
        super().__init__()
        self.__encoder = encoder
        self.__arduino = devices.get_device("arduino")
        self.__water_counter = 0
        # Initialize the state machine
        self.__machine = PoupoolModel(model=self, states=Arduino.states, initial="halt")

        self.__machine.add_transition("run", "halt", "run")
        self.__machine.add_transition("halt", "run", "halt")

    def cover_open(self):
        self.__arduino.cover_open()

    def cover_close(self):
        self.__arduino.cover_close()

    def cover_stop(self):
        self.__arduino.cover_stop()

    def cover_position(self):
        return self.__arduino.cover_position

    def water_counter(self):
        return self.__water_counter

    def on_enter_halt(self):
        logger.info("Entering halt state")
        self.cover_stop()

    @do_repeat()
    def on_enter_run(self):
        logger.info("Entering run state")

    @repeat(delay=STATE_REFRESH_DELAY)
    def do_repeat_run(self):
        # Water counter
        value = self.__arduino.water_counter
        if value is not None:
            self.__water_counter = value
            self.__encoder.water_counter(value)
        else:
            logger.error("Unable to read water counter. Not updating the value")
