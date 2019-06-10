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

from pykka._threading import ThreadingFuture
import pytest


@pytest.fixture
def encoder(mocker):
    return mocker.Mock()


@pytest.fixture
def devices(mocker):
    from controller.device import DeviceRegistry, PumpDevice
    registry = DeviceRegistry()
    pump = mocker.Mock(PumpDevice)
    type(pump).name = PropertyMock(return_value="swim")
    registry.add_pump(pump)
    return registry


@pytest.fixture
def filtration(mocker):
    from controller.filtration import Filtration
    return mocker.Mock(Filtration)


@pytest.fixture
def swim(mocker, encoder, devices, filtration):
    from controller.swim import Swim
    proxy = Swim.start(None, encoder, devices).proxy()
    # We suppose get_actor always return the filtration actor
    proxy.get_actor = mocker.Mock(return_value=filtration)
    yield proxy
    proxy.stop()


class TestSwim:

    def test_registered(self, swim):
        assert swim.get_actor("Swim") is not None

    def test_initial_state(self, swim):
        assert swim.is_halt().get()

    def test_continuous_state(self, mocker, swim, devices, filtration):
        # Filtration
        future = mocker.Mock(ThreadingFuture)
        filtration.is_overflow_normal = mocker.Mock(return_value=future)
        future.get = mocker.Mock(return_value=True)
        # Devices
        pump = devices.get_pump("swim")
        pump.speed = mocker.Mock()
        pump.off = mocker.Mock()
        # Set speed
        pump_speed = 25
        swim.speed(pump_speed).get()
        # Set continuous mode
        swim.continuous().get()
        assert swim.is_continuous().get()
        pump.speed.assert_called_once_with(pump_speed)
        # Go back to halt state
        swim.halt().get()
        assert swim.is_halt().get()
        pump.off.assert_called_once_with()
