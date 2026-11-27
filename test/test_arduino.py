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

from unittest.mock import PropertyMock

import pytest

from controller.arduino import Arduino
from controller.device import ArduinoDevice, DeviceRegistry


@pytest.fixture
def encoder(mocker):
    return mocker.Mock()


@pytest.fixture
def arduino_device(mocker):
    device = mocker.Mock(ArduinoDevice)
    type(device).name = PropertyMock(return_value="arduino")
    type(device).cover_position = PropertyMock(return_value=42)
    type(device).water_counter = PropertyMock(return_value=None)
    return device


@pytest.fixture
def devices(arduino_device):
    registry = DeviceRegistry()
    registry.add_device(arduino_device)
    return registry


@pytest.fixture
def arduino(mocker, encoder, devices):
    mocker.patch.object(Arduino, "do_delay")
    proxy = Arduino.start(encoder, devices).proxy()
    yield proxy
    proxy.stop().get()


class TestArduino:
    def test_initial_state(self, arduino):
        assert arduino.is_halt().get()
        assert arduino.water_counter().get() == 0

    def test_cover_delegation(self, arduino, arduino_device):
        arduino.cover_open().get()
        arduino_device.cover_open.assert_called_once_with()

        arduino.cover_close().get()
        arduino_device.cover_close.assert_called_once_with()

        arduino.cover_stop().get()
        arduino_device.cover_stop.assert_called_once_with()

        assert arduino.cover_position().get() == 42

    def test_restore_water_counter(self, arduino):
        arduino.restore_water_counter(500).get()
        assert arduino.water_counter().get() == 500

    def test_run_and_water_counter_lifecycle(self, mocker, arduino, arduino_device, encoder):
        do_delay_mock = mocker.patch.object(Arduino, "do_delay")
        arduino.restore_water_counter(500).get()

        # First valid reading sets baseline without changing counter or publishing
        type(arduino_device).water_counter = PropertyMock(return_value=100)
        arduino.run().get()
        # Flush deferred do_repeat_run queued by on_enter_run
        assert arduino.is_run().get()
        assert arduino.water_counter().get() == 500
        encoder.water_counter.assert_not_called()
        do_delay_mock.assert_called_once_with(Arduino.STATE_REFRESH_DELAY, "do_repeat_run")

        # Unchanged reading does not update or publish
        do_delay_mock.reset_mock()
        arduino.do_repeat_run().get()
        assert arduino.water_counter().get() == 500
        encoder.water_counter.assert_not_called()
        do_delay_mock.assert_called_once_with(Arduino.STATE_REFRESH_DELAY, "do_repeat_run")

        # Increased reading adds delta and publishes with retain=True
        do_delay_mock.reset_mock()
        type(arduino_device).water_counter = PropertyMock(return_value=115)
        arduino.do_repeat_run().get()
        assert arduino.water_counter().get() == 515
        encoder.water_counter.assert_called_once_with(515, retain=True)
        do_delay_mock.assert_called_once_with(Arduino.STATE_REFRESH_DELAY, "do_repeat_run")

        # None reading logs error and keeps last total
        do_delay_mock.reset_mock()
        encoder.reset_mock()
        type(arduino_device).water_counter = PropertyMock(return_value=None)
        arduino.do_repeat_run().get()
        assert arduino.water_counter().get() == 515
        encoder.water_counter.assert_not_called()
        do_delay_mock.assert_called_once_with(Arduino.STATE_REFRESH_DELAY, "do_repeat_run")

        # Transition to halt stops the cover
        arduino.halt().get()
        assert arduino.is_halt().get()
        arduino_device.cover_stop.assert_called_once_with()
