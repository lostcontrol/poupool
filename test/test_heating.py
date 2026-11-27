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

from controller.device import DeviceRegistry, SwitchDevice
from controller.heating import Heater, Heating


@pytest.fixture
def temperature(mocker):
    temp_proxy = mocker.Mock()
    temps = {"temperature_local": 10.0, "temperature_pool": 22.0, "temperature_air": 20.0}
    temp_proxy.get_temperature.side_effect = lambda key: mocker.Mock(get=mocker.Mock(return_value=temps[key]))
    temp_proxy.temps = temps
    return temp_proxy


@pytest.fixture
def heater_switch(mocker):
    switch = mocker.Mock(SwitchDevice)
    type(switch).name = PropertyMock(return_value="heater")
    return switch


@pytest.fixture
def heater(mocker, temperature, heater_switch):
    mocker.patch.object(Heater, "do_delay")
    proxy = Heater.start(temperature, heater_switch).proxy()
    yield proxy
    proxy.stop().get()


class TestHeater:
    def test_without_heater_cannot_wait(self, mocker, temperature):
        mocker.patch.object(Heater, "do_delay")
        proxy = Heater.start(temperature, None).proxy()
        try:
            assert not proxy.has_heater().get()
            proxy.wait().get()
            assert proxy.is_halt().get()
        finally:
            proxy.stop().get()

    def test_waiting_heating_and_halt_lifecycle(self, mocker, heater, temperature, heater_switch):
        do_delay_mock = mocker.patch.object(Heater, "do_delay")
        assert heater.has_heater().get()
        assert heater.is_halt().get()

        heater.setpoint(10.0).get()
        temperature.temps["temperature_local"] = 10.0 - Heater.HYSTERESIS_DOWN
        heater.wait().get()
        # Flush deferred do_repeat_waiting queued by on_enter_waiting
        assert heater.is_waiting().get()
        do_delay_mock.assert_called_once_with(Heater.STATE_REFRESH_DELAY, "do_repeat_waiting")

        # Below setpoint - hysteresis_down transitions to heating
        do_delay_mock.reset_mock()
        temperature.temps["temperature_local"] = 10.0 - Heater.HYSTERESIS_DOWN - 0.5
        heater.do_repeat_waiting().get()
        assert heater.is_heating().get()
        # Flush deferred do_repeat_heating queued by on_enter_heating
        assert heater.is_heating().get()
        heater_switch.on.assert_called_once_with()
        do_delay_mock.assert_called_once_with(Heater.STATE_REFRESH_DELAY, "do_repeat_heating")

        # None temperature keeps heating
        do_delay_mock.reset_mock()
        temperature.temps["temperature_local"] = None
        heater.do_repeat_heating().get()
        assert heater.is_heating().get()
        do_delay_mock.assert_called_once_with(Heater.STATE_REFRESH_DELAY, "do_repeat_heating")

        # Above setpoint + hysteresis_up transitions back to waiting
        temperature.temps["temperature_local"] = 10.0 + Heater.HYSTERESIS_UP + 0.5
        heater.do_repeat_heating().get()
        assert heater.is_waiting().get()
        # Flush deferred do_repeat_waiting
        assert heater.is_waiting().get()
        heater_switch.off.assert_called_once_with()

        # None temperature in waiting triggers heating
        heater_switch.on.reset_mock()
        temperature.temps["temperature_local"] = None
        heater.do_repeat_waiting().get()
        assert heater.is_heating().get()
        assert heater.is_heating().get()
        heater_switch.on.assert_called_once_with()

        # Halt from heating turns heater off
        heater_switch.off.reset_mock()
        heater.halt().get()
        assert heater.is_halt().get()
        assert heater_switch.off.call_count >= 1


@pytest.fixture
def encoder(mocker):
    return mocker.Mock()


@pytest.fixture
def heating_valve(mocker):
    valve = mocker.Mock(SwitchDevice)
    type(valve).name = PropertyMock(return_value="heating")
    return valve


@pytest.fixture
def heating_devices(heating_valve):
    registry = DeviceRegistry()
    registry.add_valve(heating_valve)
    return registry


@pytest.fixture
def filtration(mocker):
    actor = mocker.Mock()
    actor.is_eco_waiting.return_value.get.return_value = True
    actor.is_eco_normal.return_value.get.return_value = False
    actor.is_heating_running.return_value.get.return_value = True
    return actor


@pytest.fixture
def heating_setup(mocker, temperature, encoder, heating_devices, filtration):
    mocker.patch.object(Heating, "do_delay")
    mocker.patch.object(Heating, "get_actor", return_value=filtration)
    with freeze_time("2026-06-01 10:00:00") as frozen_time:
        proxy = Heating.start(temperature, encoder, heating_devices).proxy()
        yield proxy, frozen_time
        proxy.stop().get()


class TestHeating:
    def test_waiting_guard_conditions(self, mocker, heating_setup, temperature, encoder, heating_valve, filtration):
        heating, frozen_time = heating_setup
        do_delay_mock = mocker.patch.object(Heating, "do_delay")

        # Disable blocks waiting -> heating
        heating.enable(False).get()
        heating.wait().get()
        assert heating.is_waiting().get()
        heating_valve.off.assert_called_once_with()
        encoder.heating_state.assert_called_with("waiting")
        do_delay_mock.assert_called_once_with(Heating.STATE_REFRESH_DELAY, "do_repeat_waiting")

        # Re-enable, but schedule in the future via start_hour(14)
        heating.enable(True).get()
        heating.start_hour(14).get()
        do_delay_mock.reset_mock()
        heating.do_repeat_waiting().get()
        assert heating.is_waiting().get()
        do_delay_mock.assert_called_once_with(Heating.STATE_REFRESH_DELAY, "do_repeat_waiting")

        # Setpoint change pulls next_start back by 1 day; advance past 14:00
        heating.setpoint(26.0).get()
        frozen_time.tick(delta=timedelta(hours=5))  # 15:00

        # Pool already warm enough -> reschedules for next day
        do_delay_mock.reset_mock()
        temperature.temps["temperature_pool"] = 26.0 + Heating.HYSTERESIS_DOWN
        heating.do_repeat_waiting().get()
        assert heating.is_waiting().get()
        do_delay_mock.assert_called_once_with(Heating.STATE_REFRESH_DELAY, "do_repeat_waiting")

        # Call setpoint when next_start > now to pull back to today, with pool cold but air too cold
        heating.setpoint(26.0).get()
        heating.min_temp(18).get()
        temperature.temps["temperature_pool"] = 22.0
        temperature.temps["temperature_air"] = 16.0
        do_delay_mock.reset_mock()
        heating.do_repeat_waiting().get()
        assert heating.is_waiting().get()
        do_delay_mock.assert_called_once_with(Heating.STATE_REFRESH_DELAY, "do_repeat_waiting")

        # Air warm enough, but filtration not ready
        temperature.temps["temperature_air"] = 20.0
        filtration.is_eco_waiting.return_value.get.return_value = False
        filtration.is_eco_normal.return_value.get.return_value = False
        do_delay_mock.reset_mock()
        heating.do_repeat_waiting().get()
        assert heating.is_waiting().get()
        do_delay_mock.assert_called_once_with(Heating.STATE_REFRESH_DELAY, "do_repeat_waiting")

        # Filtration ready, but heat() does not leave filtration in heating_running
        filtration.is_eco_normal.return_value.get.return_value = True
        filtration.is_heating_running.return_value.get.return_value = False
        do_delay_mock.reset_mock()
        heating.do_repeat_waiting().get()
        filtration.heat.assert_called_once_with()
        assert heating.is_waiting().get()
        do_delay_mock.assert_called_once_with(Heating.STATE_REFRESH_DELAY, "do_repeat_waiting")

    def test_heating_cycle_duration_and_recovering(
        self, mocker, heating_setup, temperature, encoder, heating_valve, filtration
    ):
        heating, frozen_time = heating_setup
        do_delay_mock = mocker.patch.object(Heating, "do_delay")

        heating.total_seconds(100).get()
        heating.setpoint(26.0).get()
        heating.min_temp(15).get()
        temperature.temps["temperature_pool"] = 22.0
        temperature.temps["temperature_air"] = 20.0

        # Waiting -> Heating
        heating.wait().get()
        assert heating.is_heating().get()
        # Flush deferred do_repeat_heating
        assert heating.is_heating().get()
        heating_valve.on.assert_called_once_with()
        encoder.heating_state.assert_any_call("heating")
        do_delay_mock.assert_called_with(Heating.STATE_REFRESH_DELAY, "do_repeat_heating")

        # Advance 60s while still needing heat
        frozen_time.tick(delta=timedelta(seconds=60))
        do_delay_mock.reset_mock()
        heating.do_repeat_heating().get()
        assert heating.is_heating().get()
        do_delay_mock.assert_called_once_with(Heating.STATE_REFRESH_DELAY, "do_repeat_heating")

        # Pool reaches setpoint + HYSTERESIS_UP -> transitions to recovering
        temperature.temps["temperature_pool"] = 26.0 + Heating.HYSTERESIS_UP
        do_delay_mock.reset_mock()
        heating.do_repeat_heating().get()
        assert heating.is_recovering().get()

        encoder.heating_total__seconds.assert_called_once_with(160, retain=True)
        heating_valve.off.assert_called()
        filtration.heating_delay.defer.assert_called_once_with()
        encoder.heating_state.assert_any_call("recovering")
        do_delay_mock.assert_called_once_with(Heating.RECOVER_PERIOD, "recover_done")

        # recover_done -> waiting
        heating.recover_done().get()
        assert heating.is_waiting().get()
        assert heating.is_waiting().get()

    @pytest.mark.parametrize(
        "reason",
        ["disable", "pool_none", "air_too_cold"],
    )
    def test_heating_stops_on_exit_conditions(self, heating_setup, temperature, filtration, reason):
        heating, frozen_time = heating_setup
        temperature.temps["temperature_pool"] = 22.0
        temperature.temps["temperature_air"] = 20.0
        filtration.is_heating_running.return_value.get.return_value = True

        heating.wait().get()
        assert heating.is_heating().get()
        assert heating.is_heating().get()

        frozen_time.tick(delta=timedelta(seconds=10))
        if reason == "disable":
            heating.enable(False).get()
        elif reason == "pool_none":
            temperature.temps["temperature_pool"] = None
        elif reason == "air_too_cold":
            temperature.temps["temperature_air"] = 15 - Heating.HYSTERESIS_MIN_TEMP - 0.1

        filtration.is_heating_running.return_value.get.return_value = False
        heating.do_repeat_heating().get()
        assert heating.is_recovering().get()
        filtration.heating_delay.defer.assert_not_called()

    def test_forcing_and_halt(self, heating_setup, encoder, heating_valve):
        heating, frozen_time = heating_setup
        heating.total_seconds(10).get()

        heating.force().get()
        assert heating.is_forcing().get()
        heating_valve.on.assert_called_once_with()
        encoder.heating_state.assert_called_with("heating")

        frozen_time.tick(delta=timedelta(seconds=25))
        heating.wait().get()
        assert heating.is_recovering().get()
        heating_valve.off.assert_called()
        encoder.heating_total__seconds.assert_called_once_with(35, retain=True)

        heating.halt().get()
        assert heating.is_halt().get()
        encoder.heating_state.assert_called_with("halt")
