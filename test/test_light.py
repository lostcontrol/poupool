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

from controller.device import DeviceRegistry, SwitchDevice
from controller.light import Light


@pytest.fixture
def encoder(mocker):
    return mocker.Mock()


@pytest.fixture
def light_valve(mocker):
    valve = mocker.Mock(SwitchDevice)
    type(valve).name = PropertyMock(return_value="light")
    return valve


@pytest.fixture
def devices(light_valve):
    registry = DeviceRegistry()
    registry.add_valve(light_valve)
    return registry


@pytest.fixture
def light(encoder, devices):
    proxy = Light.start(encoder, devices).proxy()
    yield proxy
    proxy.stop().get()


class TestLight:
    def test_initial_state(self, light):
        assert light.is_halt().get()

    def test_on_and_halt(self, light, encoder, light_valve):
        light.on().get()
        assert light.is_on().get()
        encoder.light_state.assert_called_once_with("on")
        light_valve.on.assert_called_once_with()

        encoder.reset_mock()
        light_valve.reset_mock()

        light.halt().get()
        assert light.is_halt().get()
        encoder.light_state.assert_called_once_with("halt")
        light_valve.off.assert_called_once_with()

    def test_invalid_transitions_ignored(self, light, encoder, light_valve):
        light.halt().get()
        assert light.is_halt().get()
        encoder.light_state.assert_not_called()
        light_valve.off.assert_not_called()

        light.on().get()
        encoder.reset_mock()
        light_valve.reset_mock()

        light.on().get()
        assert light.is_on().get()
        encoder.light_state.assert_not_called()
        light_valve.on.assert_not_called()
