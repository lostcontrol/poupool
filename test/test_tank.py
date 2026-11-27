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
