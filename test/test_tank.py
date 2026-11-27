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

from datetime import timedelta
from unittest.mock import PropertyMock

import pytest
from freezegun import freeze_time

from controller.tank import Tank


@pytest.fixture
def encoder(mocker):
    return mocker.Mock()


@pytest.fixture
def tank_sensor(mocker):
    from controller.device import SensorDevice

    sensor = mocker.Mock(SensorDevice)
    type(sensor).name = PropertyMock(return_value="tank")
    type(sensor).value = PropertyMock(return_value=55.0)
    return sensor


@pytest.fixture
def devices(mocker, tank_sensor):
    from controller.device import DeviceRegistry, SwitchDevice

    registry = DeviceRegistry()
    registry.add_sensor(tank_sensor)
    valve = mocker.Mock(SwitchDevice)
    type(valve).name = PropertyMock(return_value="main")
    registry.add_valve(valve)
    return registry


@pytest.fixture
def tank(encoder, devices):
    from controller.tank import Tank

    proxy = Tank.start(encoder, devices).proxy()
    yield proxy
    proxy.stop()


class TestTank:
    def test_get_height_lifecycle(self, tank, tank_sensor):
        assert tank.is_halt().get()
        assert tank.get_height().get() is None

        tank.fill().get()
        assert tank.is_normal().get()
        assert tank.get_height().get() == 55.0

        type(tank_sensor).value = PropertyMock(return_value=95.0)
        tank.high().get()
        assert tank.is_high().get()
        assert tank.get_height().get() == 95.0

        tank.halt().get()
        assert tank.is_halt().get()
        assert tank.get_height().get() is None


@pytest.fixture
def filtration_mock(mocker):
    return mocker.Mock()


@pytest.fixture
def tank_lifecycle(mocker, encoder, devices, filtration_mock):
    mocker.patch.object(Tank, "do_delay")
    mocker.patch.object(Tank, "get_actor", return_value=filtration_mock)
    proxy = Tank.start(encoder, devices).proxy()
    yield proxy
    proxy.stop().get()


class TestTankLifecycle:
    def test_fill_to_low_to_normal_to_high_and_back(self, mocker, tank_lifecycle, tank_sensor, devices):
        do_delay_mock = mocker.patch.object(Tank, "do_delay")
        main_valve = devices.get_valve("main")

        # Enter fill below levels_too_low -> stays in fill with main valve ON
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_too_low - 2))
        tank_lifecycle.fill().get()
        assert tank_lifecycle.is_fill().get()
        # Flush deferred do_repeat_fill
        assert tank_lifecycle.is_fill().get()
        main_valve.on.assert_called()
        do_delay_mock.assert_called_with(Tank.STATE_REFRESH_DELAY / 2, "do_repeat_fill")

        # Height rises above levels_too_low -> transitions to low
        do_delay_mock.reset_mock()
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_too_low + 2))
        tank_lifecycle.do_repeat_fill().get()
        assert tank_lifecycle.is_low().get()
        # Flush deferred do_repeat_low
        assert tank_lifecycle.is_low().get()
        do_delay_mock.assert_called_with(Tank.STATE_REFRESH_DELAY / 2, "do_repeat_low")

        # Height rises to eco low + hysteresis -> transitions to normal
        do_delay_mock.reset_mock()
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_eco["low"] + Tank.hysteresis))
        tank_lifecycle.do_repeat_low().get()
        assert tank_lifecycle.is_normal().get()
        # Flush deferred do_repeat_normal -> middle height stays in normal
        assert tank_lifecycle.is_normal().get()
        main_valve.off.assert_called()
        do_delay_mock.assert_called_with(Tank.STATE_REFRESH_DELAY, "do_repeat_normal")

        # Height drops below eco low - hysteresis -> transitions back to low
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_eco["low"] - Tank.hysteresis - 1))
        tank_lifecycle.do_repeat_normal().get()
        assert tank_lifecycle.is_low().get()
        assert tank_lifecycle.is_low().get()

        # Return to normal, then jump to eco high + hysteresis -> transitions to high
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_eco["low"] + Tank.hysteresis))
        tank_lifecycle.do_repeat_low().get()
        assert tank_lifecycle.is_normal().get()
        assert tank_lifecycle.is_normal().get()

        do_delay_mock.reset_mock()
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_eco["high"] + Tank.hysteresis))
        tank_lifecycle.do_repeat_normal().get()
        assert tank_lifecycle.is_high().get()
        # Flush deferred do_repeat_high -> stays in high
        assert tank_lifecycle.is_high().get()
        do_delay_mock.assert_called_with(Tank.STATE_REFRESH_DELAY, "do_repeat_high")

        # Height drops below eco high - hysteresis -> transitions back to normal
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_eco["high"] - Tank.hysteresis - 1))
        tank_lifecycle.do_repeat_high().get()
        assert tank_lifecycle.is_normal().get()
        assert tank_lifecycle.is_normal().get()

    def test_fill_timeout_halts_filtration(self, tank_lifecycle, tank_sensor, filtration_mock):
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_too_low - 2))
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            tank_lifecycle.fill().get()
            assert tank_lifecycle.is_fill().get()
            frozen_time.tick(delta=timedelta(hours=2, seconds=1))
            tank_lifecycle.do_repeat_fill().get()
            filtration_mock.halt.defer.assert_called_once_with()

    def test_low_safety_halts_on_too_low_or_timeout(self, tank_lifecycle, tank_sensor, filtration_mock):
        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_too_low - 2))
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            tank_lifecycle.fill().get()
            assert tank_lifecycle.is_fill().get()
            type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_too_low + 2))
            tank_lifecycle.do_repeat_fill().get()
            assert tank_lifecycle.is_low().get()
            assert tank_lifecycle.is_low().get()

            # Drop below levels_too_low -> halts filtration
            type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_too_low - 1))
            tank_lifecycle.do_repeat_low().get()
            filtration_mock.halt.defer.assert_called_once_with()

            # Timeout > 6 hours in low -> halts filtration
            filtration_mock.reset_mock()
            type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_too_low + 2))
            frozen_time.tick(delta=timedelta(hours=6, seconds=1))
            tank_lifecycle.do_repeat_low().get()
            filtration_mock.halt.defer.assert_called_once_with()

    def test_set_mode_overflow_and_eco(self, tank_lifecycle, tank_sensor):
        tank_lifecycle.set_mode("overflow").get()
        assert tank_lifecycle.levels.get() == Tank.levels_overflow

        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_overflow["low"] + Tank.hysteresis))
        tank_lifecycle.fill().get()
        assert tank_lifecycle.is_normal().get()
        assert tank_lifecycle.is_normal().get()

        type(tank_sensor).value = PropertyMock(return_value=float(Tank.levels_overflow["high"] + Tank.hysteresis))
        tank_lifecycle.do_repeat_normal().get()
        assert tank_lifecycle.is_high().get()

        tank_lifecycle.set_mode("eco").get()
        assert tank_lifecycle.levels.get() == Tank.levels_eco

    def test_force_empty_behavior(self, tank_lifecycle, tank_sensor, filtration_mock):
        # Enable in halt blocks fill()
        tank_lifecycle.force_empty(True).get()
        assert tank_lifecycle.is_force_empty().get()
        tank_lifecycle.fill().get()
        assert tank_lifecycle.is_halt().get()

        # Disable in halt triggers fill()
        type(tank_sensor).value = PropertyMock(return_value=55.0)
        tank_lifecycle.force_empty(False).get()
        assert not tank_lifecycle.is_force_empty().get()
        assert tank_lifecycle.is_normal().get()

        # Enable when not in halt stops filtration (only on transition from False to True)
        tank_lifecycle.force_empty(True).get()
        filtration_mock.halt.defer.assert_called_once_with()
        filtration_mock.reset_mock()
        tank_lifecycle.force_empty(True).get()
        filtration_mock.halt.defer.assert_not_called()
