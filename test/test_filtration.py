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

import pykka
import pytest
from freezegun import freeze_time

from controller.device import DeviceRegistry, PumpDevice, SwitchDevice
from controller.filtration import Filtration, OverflowStandbyMonitor, StandbyOverflowMonitor


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


class TestOverflowStandbyMonitor:
    @pytest.fixture
    def monitor(self):
        return OverflowStandbyMonitor(
            variation_threshold=2.0,
            window=timedelta(seconds=60),
            inactivity_delay=timedelta(minutes=30),
        )

    def test_triggers_after_inactivity_delay_with_stable_level(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)

        for step in range(60):
            assert not monitor.update(start + timedelta(seconds=step * 30), 50.0)

        assert monitor.update(start + timedelta(minutes=30), 50.0)

    def test_triggers_with_small_noise_below_threshold(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        levels = [50.0, 50.7, 49.5, 50.3]

        for step in range(60):
            assert not monitor.update(start + timedelta(seconds=step * 30), levels[step % len(levels)])

        assert monitor.update(start + timedelta(minutes=30), 50.1)

    def test_resets_timer_on_variation_at_or_above_threshold(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)

        for step in range(41):
            assert not monitor.update(start + timedelta(seconds=step * 30), 50.0)

        disturbance = start + timedelta(minutes=20, seconds=30)
        assert not monitor.update(disturbance, 52.0)

        for step in range(1, 60):
            assert not monitor.update(disturbance + timedelta(seconds=step * 30), 52.0)

        assert monitor.update(disturbance + timedelta(minutes=30), 52.0)

    def test_allows_slow_gradual_drift_such_as_evaporation(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)

        # -0.1% per minute totals -3.0% over 30 min, but only 0.1% per 60s window
        for step in range(30):
            assert not monitor.update(start + timedelta(minutes=step), 60.0 - 0.1 * step)

        assert monitor.update(start + timedelta(minutes=30), 57.0)

    def test_ignores_brief_none_reading_without_resetting(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)

        assert not monitor.update(start, 50.0)
        assert not monitor.update(start + timedelta(seconds=30), None)
        assert not monitor.update(start + timedelta(seconds=60), 50.0)

        for step in range(3, 60):
            assert not monitor.update(start + timedelta(seconds=step * 30), 50.0)

        assert monitor.update(start + timedelta(minutes=30), 50.0)

    def test_resets_after_long_gap_of_none_readings(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)

        assert not monitor.update(start, 50.0)
        assert not monitor.update(start + timedelta(seconds=30), None)
        assert not monitor.update(start + timedelta(seconds=60), None)

        resumed = start + timedelta(seconds=90)
        assert not monitor.update(resumed, 50.0)

        for step in range(1, 60):
            assert not monitor.update(resumed + timedelta(seconds=step * 30), 50.0)

        assert monitor.update(resumed + timedelta(minutes=30), 50.0)

    def test_reset_clears_samples_and_restarts_timer(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)

        for step in range(51):
            assert not monitor.update(start + timedelta(seconds=step * 30), 50.0)

        monitor.reset()
        restarted = start + timedelta(minutes=25, seconds=30)
        assert not monitor.update(restarted, 50.0)

        for step in range(1, 60):
            assert not monitor.update(restarted + timedelta(seconds=step * 30), 50.0)

        assert monitor.update(restarted + timedelta(minutes=30), 50.0)

    def test_single_sample_never_triggers_even_with_zero_delay(self):
        monitor = OverflowStandbyMonitor(
            variation_threshold=2.0,
            window=timedelta(seconds=60),
            inactivity_delay=timedelta(0),
        )
        start = datetime(2026, 6, 1, 12, 0, 0)

        assert not monitor.update(start, 50.0)
        assert monitor.update(start + timedelta(seconds=10), 50.0)


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


class TestFiltrationAutoStandby:
    def __enter_overflow_normal(self, filtration):
        filtration.eco().get()
        filtration.overflow().get()
        filtration.opened().get()
        filtration.overflow().get()
        assert filtration.is_overflow_normal().get()

    def __advance_stable(self, frozen_time, filtration, minutes: float, step_seconds: int = 30) -> None:
        steps = int(minutes * 60 // step_seconds)
        for _ in range(steps):
            frozen_time.tick(delta=timedelta(seconds=step_seconds))
            filtration.do_repeat_overflow_normal().get()

    def test_switches_to_standby_when_tank_level_stable_for_delay(self, filtration):
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_overflow_normal(filtration)

            self.__advance_stable(frozen_time, filtration, minutes=29.5)
            assert filtration.is_overflow_normal().get()

            frozen_time.tick(delta=timedelta(seconds=30))
            filtration.do_repeat_overflow_normal().get()
            assert filtration.is_standby_normal().get()

    def test_resets_countdown_on_tank_disturbance(self, filtration, mocked_actors):
        tank = mocked_actors["Tank"]
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_overflow_normal(filtration)

            self.__advance_stable(frozen_time, filtration, minutes=20)
            assert filtration.is_overflow_normal().get()

            frozen_time.tick(delta=timedelta(seconds=30))
            tank.get_height.return_value.get.return_value = 53.0
            filtration.do_repeat_overflow_normal().get()
            assert filtration.is_overflow_normal().get()

            self.__advance_stable(frozen_time, filtration, minutes=29.5)
            assert filtration.is_overflow_normal().get()

            frozen_time.tick(delta=timedelta(seconds=30))
            filtration.do_repeat_overflow_normal().get()
            assert filtration.is_standby_normal().get()

    def test_stays_in_overflow_when_auto_standby_disabled(self, filtration):
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_overflow_normal(filtration)
            filtration.auto_standby(False).get()

            self.__advance_stable(frozen_time, filtration, minutes=35)
            assert filtration.is_overflow_normal().get()

    def test_reenabling_auto_standby_restarts_countdown(self, filtration):
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_overflow_normal(filtration)
            filtration.auto_standby(False).get()

            self.__advance_stable(frozen_time, filtration, minutes=35)
            assert filtration.is_overflow_normal().get()

            filtration.auto_standby(True).get()
            # First tick after reset seeds the new stability timer
            frozen_time.tick(delta=timedelta(seconds=30))
            filtration.do_repeat_overflow_normal().get()

            self.__advance_stable(frozen_time, filtration, minutes=29.5)
            assert filtration.is_overflow_normal().get()

            frozen_time.tick(delta=timedelta(seconds=30))
            filtration.do_repeat_overflow_normal().get()
            assert filtration.is_standby_normal().get()

    def test_stays_in_overflow_while_swim_pump_active(self, filtration, mocked_actors):
        swim = mocked_actors["Swim"]
        swim.is_halt.return_value.get.return_value = False
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_overflow_normal(filtration)

            self.__advance_stable(frozen_time, filtration, minutes=35)
            assert filtration.is_overflow_normal().get()

            swim.is_halt.return_value.get.return_value = True
            # First tick after swim halts seeds the stability timer
            frozen_time.tick(delta=timedelta(seconds=30))
            filtration.do_repeat_overflow_normal().get()

            self.__advance_stable(frozen_time, filtration, minutes=29.5)
            assert filtration.is_overflow_normal().get()

            frozen_time.tick(delta=timedelta(seconds=30))
            filtration.do_repeat_overflow_normal().get()
            assert filtration.is_standby_normal().get()

    def test_stays_in_overflow_when_swim_query_times_out(self, filtration, mocked_actors):
        swim = mocked_actors["Swim"]
        swim.is_halt.return_value.get.side_effect = pykka.Timeout("timeout")
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_overflow_normal(filtration)

            self.__advance_stable(frozen_time, filtration, minutes=35)
            assert filtration.is_overflow_normal().get()

    def test_stays_in_overflow_when_tank_at_auto_overflow_max_level(self, filtration, mocked_actors):
        tank = mocked_actors["Tank"]
        tank.get_height.return_value.get.return_value = 90.0
        with freeze_time("2026-06-01 12:00:00") as frozen_time:
            self.__enter_overflow_normal(filtration)

            self.__advance_stable(frozen_time, filtration, minutes=35)
            assert filtration.is_overflow_normal().get()

            filtration.auto_overflow(False).get()
            # First tick after auto_overflow is disabled seeds the stability timer
            frozen_time.tick(delta=timedelta(seconds=30))
            filtration.do_repeat_overflow_normal().get()

            self.__advance_stable(frozen_time, filtration, minutes=29.5)
            assert filtration.is_overflow_normal().get()

            frozen_time.tick(delta=timedelta(seconds=30))
            filtration.do_repeat_overflow_normal().get()
            assert filtration.is_standby_normal().get()
