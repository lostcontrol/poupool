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

import pytest
from unittest.mock import call


@pytest.fixture
def gpio(mocker):
    return mocker.Mock()


@pytest.fixture
def dac(mocker):
    return mocker.Mock()


PIN = 11


@pytest.fixture
def swim_pump_device(gpio, dac):
    from controller.device import SwimPumpDevice
    return SwimPumpDevice("swim", gpio, PIN, dac)


class TestSwimPumpDevice:

    def test_name(self, swim_pump_device):
        assert swim_pump_device.name == "swim"

    def test_on(self, gpio, dac, swim_pump_device):
        swim_pump_device.on()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        dac.normalized_value.assert_called_once_with(1)

    def test_off(self, gpio, dac, swim_pump_device):
        swim_pump_device.off()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, True)])
        dac.normalized_value.assert_called_once_with(0)

    @pytest.mark.parametrize("speed", range(0, 101, 25))
    def test_valid_speed(self, gpio, dac, swim_pump_device, speed):
        swim_pump_device.speed(speed)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, True if speed == 0 else False)])
        dac.normalized_value.assert_called_once_with(speed / 100)

    @pytest.mark.parametrize("speed", [-1, 101, 999])
    def test_invalid_speed(self, swim_pump_device, speed):
        with pytest.raises(AssertionError):
            swim_pump_device.speed(speed)

    def test_same_speed_one_call(self, gpio, dac, swim_pump_device):
        for _ in range(10):
            swim_pump_device.speed(50)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        dac.normalized_value.assert_called_once_with(0.5)