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

from unittest.mock import DEFAULT, PropertyMock, call

import pytest


@pytest.fixture()
def gpio(mocker):
    return mocker.Mock()


@pytest.fixture()
def dac(mocker):
    return mocker.Mock()


PIN = 11


@pytest.fixture()
def swim_pump_device(gpio, dac):
    from controller.device import SwimPumpDevice

    return SwimPumpDevice("swim", gpio, PIN, dac)


@pytest.fixture()
def swim_pump_device_without_dac(gpio, dac):
    from controller.device import SwimPumpDevice

    dac.value.side_effect = OSError()
    return SwimPumpDevice("swim", gpio, PIN, dac)


class TestSwimPumpDevice:
    def test_name(self, swim_pump_device):
        assert swim_pump_device.name == "swim"

    def test_on(self, gpio, dac, swim_pump_device):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        swim_pump_device.on()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        normalized_value.assert_called_once_with(1)

    def test_off(self, gpio, dac, swim_pump_device):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        swim_pump_device.off()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, True)])
        normalized_value.assert_called_once_with(0)

    def test_on_without_dac(self, gpio, swim_pump_device_without_dac):
        swim_pump_device_without_dac.on()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])

    def test_off_without_dac(self, gpio, swim_pump_device_without_dac):
        swim_pump_device_without_dac.off()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, True)])

    @pytest.mark.parametrize("speed", range(0, 101, 25))
    def test_valid_speed(self, gpio, dac, swim_pump_device, speed):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        swim_pump_device.speed(speed)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, True if speed == 0 else False)])
        normalized_value.assert_called_once_with(speed / 100)

    @pytest.mark.parametrize("speed", [-1, 101, 999])
    def test_invalid_speed(self, swim_pump_device, speed):
        with pytest.raises(AssertionError):
            swim_pump_device.speed(speed)

    def test_same_speed_one_call(self, gpio, dac, swim_pump_device):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        for _ in range(10):
            swim_pump_device.speed(50)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        normalized_value.assert_called_once_with(0.5)

    def test_dac_throws_always(self, gpio, dac, swim_pump_device):
        normalized_value = PropertyMock()
        normalized_value.side_effect = OSError()
        type(dac).normalized_value = normalized_value
        swim_pump_device.speed(50)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        normalized_value.assert_called_with(0.5)
        assert normalized_value.call_count == 3

    def test_dac_throws_once(self, gpio, dac, swim_pump_device):
        def side_effect(value):
            side_effect.counter += 1
            if side_effect.counter == 1:
                raise OSError
            return DEFAULT

        side_effect.counter = 0
        normalized_value = PropertyMock()
        normalized_value.side_effect = side_effect
        type(dac).normalized_value = normalized_value
        swim_pump_device.speed(50)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        normalized_value.assert_called_with(0.5)
        assert normalized_value.call_count == 2
