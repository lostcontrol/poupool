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

from datetime import datetime, timedelta
from unittest.mock import PropertyMock

import pytest
from freezegun import freeze_time

from controller.device import DeviceRegistry, PumpDevice, SwitchDevice
from controller.filtration import Filtration, StandbyOverflowMonitor


@pytest.fixture
def encoder(mocker):
    return mocker.Mock()


@pytest.fixture
def eco_mode(encoder):
    from controller.filtration import EcoMode

    with freeze_time("1981-05-30 00:00:01"):
        return EcoMode(encoder)


class TestEcoMode:
    @pytest.mark.parametrize("period", [1, 2, 3, 4])
    def test_24h_available_10h_daily_with_period(self, period, eco_mode):
        eco_mode.tank_percentage = 0.1
        eco_mode.period = period
        eco_mode.daily = timedelta(hours=10)
        with freeze_time("1981-05-30"):
            eco_mode.compute()
        assert eco_mode.on_duration == timedelta(hours=9 / period)
        assert eco_mode.tank_duration == timedelta(hours=1 / period)
        assert eco_mode.off_duration == timedelta(hours=(24 - 10) / period)

    @pytest.mark.parametrize("period", [1, 2, 3, 4])
    def test_10h_available_10h_daily_with_period(self, period, eco_mode):
        eco_mode.tank_percentage = 0.1
        eco_mode.period = period
        eco_mode.daily = timedelta(hours=10)
        with freeze_time("1981-05-30 14:00:00"):
            eco_mode.compute()
        assert eco_mode.on_duration == timedelta(hours=9 / period)
        assert eco_mode.tank_duration == timedelta(hours=1 / period)
        assert eco_mode.off_duration == timedelta(hours=0 / period)

    def test_all_done(self, eco_mode):
        eco_mode.daily = timedelta(hours=10)
        with freeze_time("1981-05-30"):
            eco_mode.compute()

        assert not eco_mode.update(datetime(1981, 5, 30, 0, 0, 0))
        assert not eco_mode.update(datetime(1981, 5, 30, 10, 0, 0))

        assert eco_mode.filtration.duration == timedelta(hours=10)
        assert eco_mode.filtration.remaining == timedelta(hours=0)
        assert eco_mode.filtration.elapsed()

    def test_half_done(self, eco_mode):
        eco_mode.daily = timedelta(hours=10)
        with freeze_time("1981-05-30"):
            eco_mode.compute()

        assert not eco_mode.update(datetime(1981, 5, 30, 0, 0, 0))
        assert not eco_mode.update(datetime(1981, 5, 30, 5, 0, 0))

        assert eco_mode.filtration.duration == timedelta(hours=5)
        assert eco_mode.filtration.remaining == timedelta(hours=5)
        assert not eco_mode.filtration.elapsed()


class TestStandbyOverflowMonitor:
    @pytest.fixture
    def monitor(self):
        return StandbyOverflowMonitor(
            rise_threshold=5.0,
            window=timedelta(seconds=60),
            max_level=90.0,
            settle_delay=timedelta(seconds=60),
        )

    def test_ignores_changes_during_settle_delay_and_does_not_leak_samples(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        monitor.reset(start)

        # Even rapid rises or ceiling levels are ignored during settling
        assert not monitor.update(start, 40.0)
        assert not monitor.update(start + timedelta(seconds=20), 95.0)
        assert not monitor.update(start + timedelta(seconds=50), 30.0)

        # First reading at or after settle_delay must not compare against pre-settle samples (30.0)
        assert not monitor.update(start + timedelta(seconds=60), 50.0)

    def test_triggers_on_rapid_rise_after_settling(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        monitor.reset(start)

        assert not monitor.update(start + timedelta(seconds=60), 50.0)
        assert not monitor.update(start + timedelta(seconds=80), 52.0)
        assert monitor.update(start + timedelta(seconds=100), 55.0)

    def test_triggers_when_level_dips_then_rises_within_window(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        monitor.reset(start)

        assert not monitor.update(start + timedelta(seconds=60), 52.0)
        assert not monitor.update(start + timedelta(seconds=70), 49.0)
        assert monitor.update(start + timedelta(seconds=90), 54.0)

    def test_does_not_trigger_on_slow_gradual_rise(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        monitor.reset(start)

        # +1% every 20s: max rise within any 60s window is 3% (< 5%)
        for step in range(11):
            t = start + timedelta(seconds=60 + step * 20)
            assert not monitor.update(t, 40.0 + step)

    def test_triggers_at_max_level_after_settling(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        monitor.reset(start)

        assert not monitor.update(start + timedelta(seconds=30), 92.0)
        assert monitor.update(start + timedelta(seconds=60), 90.0)

    def test_ignores_none_height(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        monitor.reset(start)

        assert not monitor.update(start, None)
        assert not monitor.update(start + timedelta(seconds=60), None)
        assert not monitor.update(start + timedelta(seconds=70), 50.0)
        assert not monitor.update(start + timedelta(seconds=80), None)
        assert monitor.update(start + timedelta(seconds=90), 55.0)

    def test_reset_clears_samples_and_restarts_settle_delay(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        monitor.reset(start)

        assert not monitor.update(start + timedelta(seconds=60), 50.0)

        restarted = start + timedelta(seconds=70)
        monitor.reset(restarted)
        assert not monitor.update(restarted + timedelta(seconds=10), 60.0)
        assert not monitor.update(restarted + timedelta(seconds=60), 60.0)

    def test_zero_settle_delay(self):
        monitor = StandbyOverflowMonitor(
            rise_threshold=5.0,
            window=timedelta(seconds=60),
            max_level=90.0,
            settle_delay=timedelta(0),
        )
        start = datetime(2026, 6, 1, 12, 0, 0)
        monitor.reset(start)

        assert not monitor.update(start, 50.0)
        assert monitor.update(start + timedelta(seconds=10), 55.0)


@pytest.fixture
def filtration_devices(mocker):
    registry = DeviceRegistry()
    variable = mocker.Mock(PumpDevice)
    type(variable).name = PropertyMock(return_value="variable")
    registry.add_pump(variable)

    boost = mocker.Mock(SwitchDevice)
    type(boost).name = PropertyMock(return_value="boost")
    registry.add_pump(boost)

    for valve_name in ("gravity", "backwash", "tank", "drain"):
        valve = mocker.Mock(SwitchDevice)
        type(valve).name = PropertyMock(return_value=valve_name)
        registry.add_valve(valve)
    return registry


@pytest.fixture
def mocked_actors(mocker):
    def make_actor(*, halt: bool = True):
        actor = mocker.Mock()
        actor.is_halt.return_value.get.return_value = halt
        return actor

    tank = make_actor(halt=False)
    tank.is_low.return_value.get.return_value = False
    tank.is_fill.return_value.get.return_value = False
    tank.is_high.return_value.get.return_value = False
    tank.get_height.return_value.get.return_value = 50.0

    arduino = make_actor(halt=True)
    arduino.cover_position.return_value.get.return_value = 0

    return {
        "Tank": tank,
        "Arduino": arduino,
        "Heating": make_actor(halt=True),
        "Disinfection": make_actor(halt=True),
        "Light": make_actor(halt=True),
        "Swim": make_actor(halt=True),
    }


@pytest.fixture
def filtration(mocker, encoder, filtration_devices, mocked_actors):
    mocker.patch.object(Filtration, "get_actor", side_effect=lambda name: mocked_actors[name])
    proxy = Filtration.start(None, encoder, filtration_devices).proxy()
    yield proxy
    proxy.stop()


class TestFiltrationAutoOverflow:
    def __enter_standby_normal(self, filtration):
        filtration.eco().get()
        filtration.standby().get()
        filtration.opened().get()
        filtration.standby().get()
        assert filtration.is_standby_normal().get()

    def test_switches_to_overflow_on_rapid_tank_rise(self, filtration, mocked_actors):
        tank = mocked_actors["Tank"]
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_standby_normal(filtration)

            # During settling grace period, rapid rise does not trigger
            frozen_time.tick(delta=timedelta(seconds=30))
            tank.get_height.return_value.get.return_value = 60.0
            filtration.do_repeat_standby_normal().get()
            assert filtration.is_standby_normal().get()

            # After settling grace period, rapid rise triggers overflow
            frozen_time.tick(delta=timedelta(seconds=30))
            tank.get_height.return_value.get.return_value = 50.0
            filtration.do_repeat_standby_normal().get()
            assert filtration.is_standby_normal().get()

            frozen_time.tick(delta=timedelta(seconds=20))
            tank.get_height.return_value.get.return_value = 56.0
            filtration.do_repeat_standby_normal().get()
            assert filtration.is_overflow_normal().get()

    def test_stays_in_standby_when_auto_overflow_disabled(self, filtration, mocked_actors):
        tank = mocked_actors["Tank"]
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_standby_normal(filtration)
            filtration.auto_overflow(False).get()

            frozen_time.tick(delta=timedelta(seconds=60))
            tank.get_height.return_value.get.return_value = 50.0
            filtration.do_repeat_standby_normal().get()

            frozen_time.tick(delta=timedelta(seconds=20))
            tank.get_height.return_value.get.return_value = 95.0
            filtration.do_repeat_standby_normal().get()
            assert filtration.is_standby_normal().get()
