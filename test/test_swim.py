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
from pykka._threading import ThreadingFuture

from controller.swim import Swim


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


@pytest.fixture
def temperature(mocker):
    temp = mocker.Mock()
    temps = {"temperature_ncc": 5.0}
    temp.get_temperature.side_effect = lambda key: mocker.Mock(get=mocker.Mock(return_value=temps[key]))
    temp.temps = temps
    return temp


@pytest.fixture
def swim_filtration(mocker):
    actor = mocker.Mock()
    actor.is_overflow_normal.return_value.get.return_value = False
    actor.is_standby_normal.return_value.get.return_value = False
    actor.is_comfort.return_value.get.return_value = False
    actor.is_wintering_waiting.return_value.get.return_value = False
    actor.is_wintering_stir.return_value.get.return_value = False
    return actor


@pytest.fixture
def swim_modes(mocker, temperature, encoder, devices, swim_filtration):
    mocker.patch.object(Swim, "do_delay")
    mocker.patch.object(Swim, "get_actor", return_value=swim_filtration)
    proxy = Swim.start(temperature, encoder, devices).proxy()
    yield proxy
    proxy.stop().get()


class TestSwimModes:
    def test_blocked_when_filtration_disallows_swim(self, swim_modes):
        swim_modes.timed().get()
        assert swim_modes.is_halt().get()
        swim_modes.continuous().get()
        assert swim_modes.is_halt().get()
        swim_modes.wintering().get()
        assert swim_modes.is_halt().get()

    @pytest.mark.parametrize("method", ["is_standby_normal", "is_comfort"])
    def test_timed_mode_and_transitions(self, mocker, swim_modes, swim_filtration, devices, encoder, method):
        getattr(swim_filtration, method).return_value.get.return_value = True
        do_delay_mock = mocker.patch.object(Swim, "do_delay")
        pump = devices.get_pump("swim")

        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            swim_modes.timer(5).get()
            swim_modes.speed(65).get()
            swim_modes.timed().get()
            assert swim_modes.is_timed().get()
            # Flush deferred do_repeat_timed queued by on_enter_timed
            assert swim_modes.is_timed().get()
            encoder.swim_state.assert_called_with("timed")
            pump.speed.assert_called_with(65)
            do_delay_mock.assert_called_with(Swim.STATE_REFRESH_DELAY, "do_repeat_timed")

            # Halfway through timer -> stays timed
            frozen_time.tick(delta=timedelta(minutes=2))
            do_delay_mock.reset_mock()
            swim_modes.do_repeat_timed().get()
            assert swim_modes.is_timed().get()
            do_delay_mock.assert_called_once_with(Swim.STATE_REFRESH_DELAY, "do_repeat_timed")

            # Transition timed -> continuous -> timed
            swim_modes.continuous().get()
            assert swim_modes.is_continuous().get()
            assert swim_modes.is_continuous().get()
            encoder.swim_state.assert_called_with("continuous")

            swim_modes.timed().get()
            assert swim_modes.is_timed().get()
            assert swim_modes.is_timed().get()

            # Timer elapses -> transitions to halt
            frozen_time.tick(delta=timedelta(minutes=5))
            swim_modes.do_repeat_timed().get()
            assert swim_modes.is_halt().get()
            pump.off.assert_called()
            encoder.swim_state.assert_called_with("halt")

    def test_wintering_lifecycle(self, mocker, swim_modes, swim_filtration, temperature, devices, encoder):
        swim_filtration.is_wintering_waiting.return_value.get.return_value = True
        do_delay_mock = mocker.patch.object(Swim, "do_delay")
        pump = devices.get_pump("swim")

        with freeze_time("2026-01-15 10:00:00") as frozen_time:
            swim_modes.wintering().get()
            assert swim_modes.is_wintering_waiting().get()
            # Flush deferred do_repeat_wintering_waiting
            assert swim_modes.is_wintering_waiting().get()
            encoder.swim_state.assert_called_with("wintering_waiting")
            pump.off.assert_called()
            do_delay_mock.assert_called_with(120, "do_repeat_wintering_waiting")

            # Before WINTERING_PERIOD elapses -> stays waiting
            frozen_time.tick(delta=timedelta(seconds=Swim.WINTERING_PERIOD // 2))
            do_delay_mock.reset_mock()
            swim_modes.do_repeat_wintering_waiting().get()
            assert swim_modes.is_wintering_waiting().get()
            do_delay_mock.assert_called_once_with(120, "do_repeat_wintering_waiting")

            # After WINTERING_PERIOD, temperature above threshold -> stays waiting
            frozen_time.tick(delta=timedelta(seconds=Swim.WINTERING_PERIOD))
            temperature.temps["temperature_ncc"] = Swim.WINTERING_ONLY_BELOW + 2.0
            do_delay_mock.reset_mock()
            swim_modes.do_repeat_wintering_waiting().get()
            assert swim_modes.is_wintering_waiting().get()
            do_delay_mock.assert_called_once_with(120, "do_repeat_wintering_waiting")

            # Temperature below threshold -> transitions to wintering_stir
            temperature.temps["temperature_ncc"] = Swim.WINTERING_ONLY_BELOW
            do_delay_mock.reset_mock()
            swim_modes.do_repeat_wintering_waiting().get()
            assert swim_modes.is_wintering_stir().get()
            encoder.swim_state.assert_called_with("wintering_stir")
            pump.on.assert_called_once_with()
            do_delay_mock.assert_called_once_with(Swim.WINTERING_DURATION, "wintering_waiting")

            # Back to waiting, then None temperature also triggers stir
            swim_modes.wintering_waiting().get()
            assert swim_modes.is_wintering_waiting().get()
            assert swim_modes.is_wintering_waiting().get()
            frozen_time.tick(delta=timedelta(seconds=Swim.WINTERING_PERIOD + 1))
            temperature.temps["temperature_ncc"] = None
            swim_modes.do_repeat_wintering_waiting().get()
            assert swim_modes.is_wintering_stir().get()

            # Check filtration_is_wintering via is_wintering_stir too
            swim_filtration.is_wintering_waiting.return_value.get.return_value = False
            swim_filtration.is_wintering_stir.return_value.get.return_value = True
            assert swim_modes.filtration_is_wintering().get()

            # Halt from wintering
            swim_modes.halt().get()
            assert swim_modes.is_halt().get()
