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
from controller.filtration import (
    EcoMode,
    Filtration,
    OverflowStandbyMonitor,
    StandbyOverflowMonitor,
    StirMode,
)


@pytest.fixture
def encoder(mocker):
    return mocker.Mock()


@pytest.fixture
def eco_mode(encoder):
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

    def test_daily_property_set_current_and_elapsed_helpers(self, eco_mode):
        assert eco_mode.daily == timedelta(hours=10)
        eco_mode.set_current(timedelta(minutes=10))
        assert not eco_mode.elapsed_on()
        assert not eco_mode.elapsed_off()

        t0 = datetime(1981, 5, 30, 1, 0, 0)
        eco_mode.update(t0)
        eco_mode.update(t0 + timedelta(minutes=10))
        assert eco_mode.elapsed_on()
        assert eco_mode.elapsed_off()

    def test_compute_clamping_edges(self, eco_mode):
        # on_duration < 1h floored to 1h, tank_duration < 1m floored to 1m
        eco_mode.tank_percentage = 0.0
        eco_mode.daily = timedelta(minutes=30)
        with freeze_time("1981-05-30 00:00:00"):
            eco_mode.compute()
        assert eco_mode.tank_duration == timedelta(minutes=1)
        assert eco_mode.on_duration == timedelta(minutes=59)

        # off_duration < 0 clamped to 0 when remaining_time < daily
        eco_mode.daily = timedelta(hours=10)
        with freeze_time("1981-05-30 20:00:00"):
            eco_mode.compute()
        assert eco_mode.off_duration == timedelta()

    def test_update_daily_reset_resets_and_persists(self, eco_mode, encoder):
        eco_mode.daily = timedelta(hours=10)
        t0 = datetime(1981, 5, 30, 10, 0, 0)
        assert not eco_mode.update(t0)
        assert not eco_mode.update(t0 + timedelta(hours=2))
        assert eco_mode.filtration.duration == timedelta(hours=2)

        assert eco_mode.update(datetime(1981, 5, 31, 0, 0, 0))
        assert eco_mode.filtration.duration == timedelta()
        encoder.filtration_duration.assert_called_with("0", retain=True)


class TestStirMode:
    @pytest.fixture
    def stir_devices(self, mocker):
        registry = DeviceRegistry()
        boost = mocker.Mock(SwitchDevice)
        type(boost).name = PropertyMock(return_value="boost")
        registry.add_pump(boost)
        return registry

    def test_stir_period_duration_and_solar_elevation(self, mocker, stir_devices):
        stir = StirMode(stir_devices)
        boost = stir_devices.get_pump("boost")
        elev = mocker.patch("controller.filtration.sun.elevation")

        # Valid and invalid period/duration combinations
        stir.stir_duration(60)
        stir.stir_period(300)
        stir.stir_period(30)  # invalid: 0 < 30 < 60
        stir.stir_duration(600)  # invalid: 300 < 600

        t0 = datetime(2026, 6, 1, 12, 0, 0)
        # Below solar elevation -> does not start boost
        elev.return_value = StirMode.SOLAR_ELEVATION - 1
        stir.update(t0)
        boost.on.assert_not_called()

        # Above solar elevation -> starts boost for 60s (Timer.delay resets __last, so seed then advance 60s)
        elev.return_value = StirMode.SOLAR_ELEVATION + 5
        stir.update(t0)
        boost.on.assert_called_once_with()

        stir.update(t0 + timedelta(seconds=60))
        boost.off.assert_not_called()
        stir.update(t0 + timedelta(seconds=120))
        boost.off.assert_called_once_with()

        # clear(None) and clear(now) turn boost off
        boost.off.reset_mock()
        stir.clear(None)
        stir.clear(t0)
        assert boost.off.call_count == 2

        # period=0 disables stir
        boost.on.reset_mock()
        stir.stir_period(0)
        stir.update(t0 + timedelta(seconds=1000))
        boost.on.assert_not_called()


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

    def test_update_without_prior_reset_initializes_start(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        assert not monitor.update(start, 50.0)
        assert not monitor.update(start + timedelta(seconds=30), 60.0)
        assert monitor.update(start + timedelta(seconds=60), 90.0)


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

    def test_ignores_none_before_first_sample(self, monitor):
        start = datetime(2026, 6, 1, 12, 0, 0)
        assert not monitor.update(start, None)
        assert not monitor.update(start + timedelta(minutes=30), None)

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

    heating = make_actor(halt=True)
    heating.is_heating.return_value.get.return_value = False
    heating.is_forcing.return_value.get.return_value = False
    heating.is_recovering.return_value.get.return_value = False

    return {
        "Tank": tank,
        "Arduino": arduino,
        "Heating": heating,
        "Heater": make_actor(halt=True),
        "Disinfection": make_actor(halt=True),
        "Light": make_actor(halt=True),
        "Swim": make_actor(halt=True),
    }


@pytest.fixture
def filtration(mocker, encoder, filtration_devices, mocked_actors):
    mocker.patch.object(Filtration, "get_actor", side_effect=lambda name: mocked_actors[name])
    proxy = Filtration.start(None, encoder, filtration_devices).proxy()
    yield proxy
    proxy.stop().get()


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


@pytest.fixture
def filtration_temperature(mocker):
    temp = mocker.Mock()
    temps = {"temperature_air": 10.0}
    temp.get_temperature.side_effect = lambda key: mocker.Mock(get=mocker.Mock(return_value=temps[key]))
    temp.temps = temps
    return temp


@pytest.fixture
def filtration_actor(mocker, encoder, filtration_devices, mocked_actors, filtration_temperature):
    mocker.patch.object(Filtration, "do_delay")
    mocker.patch("controller.filtration.time.sleep")
    mocker.patch.object(Filtration, "get_actor", side_effect=lambda name: mocked_actors[name])
    with freeze_time("2026-06-01 00:00:01") as frozen_time:
        proxy = Filtration.start(filtration_temperature, encoder, filtration_devices).proxy()
        yield proxy, frozen_time
        proxy.stop().get()


class TestFiltrationStates:
    def test_startup_and_halt_with_timeout(self, filtration_actor, mocked_actors, filtration_devices):
        filtration, _ = filtration_actor
        mocked_actors["Tank"].is_halt.return_value.get.return_value = True

        # halt -> eco starts Arduino, Tank, Heating
        filtration.eco().get()
        assert filtration.is_eco_compute().get()
        mocked_actors["Arduino"].run.defer.assert_called_once_with()
        mocked_actors["Tank"].fill.defer.assert_called_once_with()
        mocked_actors["Heating"].wait.defer.assert_called_once_with()

        # Simulate all child actors running and Disinfection timing out on halt
        for name, actor in mocked_actors.items():
            actor.is_halt.return_value.get.return_value = False
            actor.halt.defer.reset_mock()
            if name == "Disinfection":
                actor.is_halt.return_value.get.side_effect = pykka.Timeout("timeout")

        filtration.halt().get()
        assert filtration.is_halt().get()
        for name in ("Disinfection", "Tank", "Arduino", "Heating", "Light", "Swim"):
            mocked_actors[name].halt.defer.assert_called_once_with()
        for pump in filtration_devices.get_pumps():
            pump.off.assert_called()
        for valve in filtration_devices.get_valves():
            valve.off.assert_called()

    def test_settings_and_reload_transitions(self, filtration_actor, mocked_actors, filtration_devices, encoder):
        filtration, _ = filtration_actor
        tank = mocked_actors["Tank"]
        disinfection = mocked_actors["Disinfection"]

        # Simple settings + eco reloaders
        filtration.backwash_backwash_duration(90).get()
        filtration.backwash_rinse_duration(45).get()
        filtration.backwash_period(1).get()  # invalid (< 2)
        filtration.backwash_period(14).get()
        filtration.backwash_last("Mon Jun  1 00:00:00 2026").get()
        filtration.stir_duration(60).get()
        filtration.stir_period(300).get()
        filtration.boost_duration(120).get()
        filtration.cover_position_eco(25).get()
        filtration.restore_duration(1800).get()

        filtration.eco().get()
        assert filtration.is_eco_compute().get()

        for call_fn in (
            lambda: filtration.duration(36000).get(),
            lambda: filtration.period(2).get(),
            lambda: filtration.tank_percentage(0.2).get(),
            lambda: filtration.reset_hour(2).get(),
        ):
            call_fn()
            # Flush reload.defer() -> eco.defer()
            assert filtration.is_eco_compute().get()

        # speed_eco reloads when in eco_normal
        filtration.eco_normal().get()
        assert filtration.is_eco_normal().get()
        filtration.speed_eco(2).get()
        assert filtration.is_eco_compute().get()

        # Standby settings, reload, speed_standby(0) halts Disinfection, auto_overflow reset & None height
        filtration.standby().get()
        filtration.opened().get()
        filtration.standby().get()
        assert filtration.is_standby_normal().get()
        filtration.auto_overflow(True).get()
        tank.get_height.return_value.get.return_value = None
        filtration.do_repeat_standby_normal().get()
        assert filtration.is_standby_normal().get()

        disinfection.is_halt.return_value.get.return_value = False
        disinfection.halt.defer.reset_mock()
        filtration.speed_standby(0).get()
        assert filtration.is_standby_normal().get()
        assert filtration.is_standby_normal().get()
        disinfection.halt.defer.assert_called()

        # Overflow settings, speed 2 starts disinfection and turns boost off, None height skips auto-standby
        disinfection.is_halt.return_value.get.return_value = True
        filtration.speed_overflow(2).get()
        filtration.overflow().get()
        assert filtration.is_overflow_normal().get()
        assert filtration.is_overflow_normal().get()
        filtration_devices.get_pump("boost").off.assert_called()
        disinfection.run.defer.assert_called()

        tank.get_height.return_value.get.return_value = None
        filtration.do_repeat_overflow_normal().get()
        assert filtration.is_overflow_normal().get()

        filtration.speed_overflow(4).get()
        assert filtration.is_overflow_normal().get()
        assert filtration.is_overflow_normal().get()
        encoder.filtration_state.assert_any_call("overflow")

    def test_opening_and_closing_cover(self, mocker, filtration_actor, mocked_actors, encoder):
        filtration, _ = filtration_actor
        do_delay_mock = mocker.patch.object(Filtration, "do_delay")
        arduino = mocked_actors["Arduino"]

        filtration.eco().get()
        assert filtration.is_eco_compute().get()

        # Open cover towards standby
        arduino.cover_position.return_value.get.return_value = 50
        filtration.standby().get()
        assert filtration.is_opening_standby().get()
        assert filtration.is_opening_standby().get()
        encoder.filtration_state.assert_called_with("opening_50")
        do_delay_mock.assert_called_with(5, "do_repeat_opening")

        do_delay_mock.reset_mock()
        arduino.cover_position.return_value.get.return_value = 100
        filtration.do_repeat_opening().get()
        encoder.filtration_state.assert_called_with("opening_100")
        do_delay_mock.assert_called_with(2, "opened")

        filtration.opened().get()
        assert filtration.is_standby_boost().get()
        mocked_actors["Tank"].set_mode.defer.assert_called_with("overflow")
        arduino.cover_stop.defer.assert_called()

        # Close cover back to eco (cover_position_eco == 0 -> delays 2s "closed")
        filtration.eco().get()
        assert filtration.is_closing().get()
        assert filtration.is_closing().get()
        encoder.filtration_state.assert_called_with("closing_100")
        do_delay_mock.assert_called_with(5, "do_repeat_closing")

        do_delay_mock.reset_mock()
        arduino.cover_position.return_value.get.return_value = 0
        filtration.do_repeat_closing().get()
        encoder.filtration_state.assert_called_with("closing_0")
        do_delay_mock.assert_called_with(2, "closed")

        # Non-zero cover_position_eco transitions directly via closed.defer()
        filtration.cover_position_eco(20).get()
        arduino.cover_position.return_value.get.return_value = 20
        filtration.do_repeat_closing().get()
        assert filtration.is_eco_compute().get()
        assert arduino.cover_stop.defer.call_count >= 2

    def test_eco_compute_starts_eco_normal_when_no_off_duration(
        self, mocker, filtration_temperature, encoder, filtration_devices, mocked_actors
    ):
        do_delay_mock = mocker.patch.object(Filtration, "do_delay")
        mocker.patch.object(Filtration, "get_actor", side_effect=lambda name: mocked_actors[name])
        with freeze_time("2026-06-01 16:00:00"):
            proxy = Filtration.start(filtration_temperature, encoder, filtration_devices).proxy()
            try:
                proxy.eco().get()
                assert proxy.is_eco_compute().get()
                do_delay_mock.assert_any_call(5, "eco_normal")
            finally:
                proxy.stop().get()

    def test_eco_substates_and_backwash_wash_rinse(
        self, mocker, filtration_actor, mocked_actors, filtration_devices, encoder
    ):
        filtration, frozen_time = filtration_actor
        do_delay_mock = mocker.patch.object(Filtration, "do_delay")
        tank = mocked_actors["Tank"]

        # Set recent backwash so backwash does not trigger yet
        filtration.backwash_last("Mon Jun  1 00:00:00 2026").get()
        filtration.eco().get()
        assert filtration.is_eco_compute().get()
        do_delay_mock.assert_called_with(5, "eco_waiting")

        # eco_waiting: normal tick, then elapsed_off -> eco_normal
        filtration.eco_waiting().get()
        assert filtration.is_eco_waiting().get()
        assert filtration.is_eco_waiting().get()
        do_delay_mock.assert_called_with(Filtration.STATE_REFRESH_DELAY, "do_repeat_eco_waiting")

        # Default compute from 00:00:01 with 10h daily / 3 periods gives off_duration = (24-10)/3 = 4h40m
        frozen_time.tick(delta=timedelta(hours=5))
        filtration.do_repeat_eco_waiting().get()
        assert filtration.is_eco_normal().get()
        assert filtration.is_eco_normal().get()

        # Normal tick in eco_normal delays 10s
        do_delay_mock.reset_mock()
        frozen_time.tick(delta=timedelta(minutes=5))
        filtration.do_repeat_eco_normal().get()
        assert filtration.is_eco_normal().get()
        do_delay_mock.assert_called_with(Filtration.STATE_REFRESH_DELAY, "do_repeat_eco_normal")

        # elapsed_on with tank_is_low() == False -> eco_tank
        frozen_time.tick(delta=timedelta(hours=3, minutes=20))
        filtration.do_repeat_eco_normal().get()
        assert filtration.is_eco_tank().get()
        assert filtration.is_eco_tank().get()
        filtration_devices.get_valve("tank").on.assert_called()

        # Normal tick in eco_tank delays 10s, then elapsed_on -> eco_waiting (exits tank valve)
        do_delay_mock.reset_mock()
        filtration.do_repeat_eco_tank().get()
        do_delay_mock.assert_called_with(Filtration.STATE_REFRESH_DELAY, "do_repeat_eco_tank")

        frozen_time.tick(delta=timedelta(minutes=30))
        filtration.do_repeat_eco_tank().get()
        assert filtration.is_eco_waiting().get()
        assert filtration.is_eco_waiting().get()
        filtration_devices.get_valve("tank").off.assert_called()

        # elapsed_on in eco_normal when tank_is_low() == True -> eco_waiting directly
        filtration.eco_normal().get()
        assert filtration.is_eco_normal().get()
        assert filtration.is_eco_normal().get()
        tank.is_low.return_value.get.return_value = True
        frozen_time.tick(delta=timedelta(hours=3, minutes=30))
        filtration.do_repeat_eco_normal().get()
        assert filtration.is_eco_waiting().get()
        assert filtration.is_eco_waiting().get()
        tank.is_low.return_value.get.return_value = False

        # Daily reset in eco_waiting -> reload -> eco_compute
        frozen_time.tick(delta=timedelta(days=1))
        filtration.do_repeat_eco_waiting().get()
        assert filtration.is_eco_compute().get()

        # Daily reset in eco_normal and eco_tank also reload
        filtration.eco_normal().get()
        assert filtration.is_eco_normal().get()
        assert filtration.is_eco_normal().get()
        frozen_time.tick(delta=timedelta(days=1))
        filtration.do_repeat_eco_normal().get()
        assert filtration.is_eco_compute().get()

        filtration.eco_normal().get()
        filtration.eco_tank().get()
        assert filtration.is_eco_tank().get()
        assert filtration.is_eco_tank().get()
        frozen_time.tick(delta=timedelta(days=1))
        filtration.do_repeat_eco_tank().get()
        assert filtration.is_eco_compute().get()

        # Backwash due (>30 days) with tank NOT high logs & stays; with tank high -> wash -> rinse -> eco
        filtration.backwash_last("Fri May  1 00:00:00 2026").get()
        filtration.eco_normal().get()
        assert filtration.is_eco_normal().get()
        assert filtration.is_eco_normal().get()  # tank.is_high() is False -> stays eco_normal

        tank.is_high.return_value.get.return_value = True
        do_delay_mock.reset_mock()
        filtration.do_repeat_eco_normal().get()
        assert filtration.is_wash_backwash().get()
        filtration_devices.get_valve("backwash").on.assert_called_once_with()
        filtration_devices.get_valve("drain").on.assert_called_once_with()
        do_delay_mock.assert_any_call(120, "rinse")

        do_delay_mock.reset_mock()
        filtration.rinse().get()
        assert filtration.is_wash_rinse().get()
        filtration_devices.get_valve("backwash").off.assert_called_once_with()
        do_delay_mock.assert_any_call(60, "eco")

        filtration.eco().get()
        assert filtration.is_eco_compute().get()
        encoder.filtration_backwash_last.assert_called_once()
        assert encoder.filtration_backwash_last.call_args.kwargs == {"retain": True}

        # Backwash due from eco_waiting also triggers wash
        tank.is_high.return_value.get.return_value = False
        filtration.backwash_last("Fri May  1 00:00:00 2026").get()
        filtration.eco_waiting().get()
        assert filtration.is_eco_waiting().get()
        tank.is_high.return_value.get.return_value = True
        filtration.do_repeat_eco_waiting().get()
        assert filtration.is_wash_backwash().get()

    def test_heating_and_heating_delays(self, mocker, filtration_actor, mocked_actors):
        filtration, _ = filtration_actor
        do_delay_mock = mocker.patch.object(Filtration, "do_delay")
        heating = mocked_actors["Heating"]

        filtration.eco().get()
        filtration.eco_waiting().get()
        assert filtration.is_eco_waiting().get()

        # heat -> heating_running -> heating_delay_none -> eco
        filtration.heat().get()
        assert filtration.is_heating_running().get()
        assert filtration.is_heating_running().get()
        do_delay_mock.assert_called_with(Filtration.STATE_REFRESH_DELAY, "do_repeat_heating_running")

        heating.is_heating.return_value.get.return_value = True
        heating.wait.defer.reset_mock()
        do_delay_mock.reset_mock()
        filtration.heating_delay().get()
        assert filtration.is_heating_delay_none().get()
        heating.wait.defer.assert_called_once_with()
        do_delay_mock.assert_called_once_with(Filtration.HEATING_DELAY_TO_ECO, "heating_delayed")

        filtration.heating_delayed().get()
        assert filtration.is_eco_compute().get()

        # heating_running -> standby -> heating_delay_standby -> opening_standby
        filtration.eco_normal().get()
        filtration.heat().get()
        assert filtration.is_heating_running().get()
        do_delay_mock.reset_mock()
        filtration.standby().get()
        assert filtration.is_heating_delay_standby().get()
        do_delay_mock.assert_called_once_with(Filtration.HEATING_DELAY_TO_OPEN, "heating_delayed")
        filtration.heating_delayed().get()
        assert filtration.is_opening_standby().get()

        # closing -> eco -> heating_running -> overflow -> heating_delay_overflow -> opening_overflow
        filtration.eco().get()
        filtration.closed().get()
        filtration.eco_normal().get()
        filtration.heat().get()
        assert filtration.is_heating_running().get()
        do_delay_mock.reset_mock()
        filtration.overflow().get()
        assert filtration.is_heating_delay_overflow().get()
        do_delay_mock.assert_called_once_with(Filtration.HEATING_DELAY_TO_OPEN, "heating_delayed")
        filtration.heating_delayed().get()
        assert filtration.is_opening_overflow().get()

    def test_standby_sweep_comfort_and_overflow(self, filtration_actor, mocked_actors, filtration_devices):
        filtration, _ = filtration_actor
        heating = mocked_actors["Heating"]
        swim = mocked_actors["Swim"]
        tank_valve = filtration_devices.get_valve("tank")

        filtration.eco().get()
        filtration.standby().get()
        filtration.opened().get()
        filtration.standby().get()
        assert filtration.is_standby_normal().get()

        # Manual boost in standby
        filtration.standby().get()
        assert filtration.is_standby_boost().get()
        filtration.standby().get()
        assert filtration.is_standby_normal().get()

        # Sweep -> standby
        filtration.sweep().get()
        assert filtration.is_sweep().get()
        filtration.standby().get()
        assert filtration.is_standby_normal().get()

        # Comfort -> reload_comfort -> force heating -> blocked standby when speed_standby == 0 -> overflow
        tank_valve.on.reset_mock()
        tank_valve.off.reset_mock()
        filtration.comfort().get()
        assert filtration.is_comfort().get()
        assert filtration.is_comfort().get()
        heating.force.defer.assert_called()
        tank_valve.off.assert_called()

        filtration.overflow_in_comfort(True).get()
        assert filtration.is_comfort().get()
        tank_valve.on.assert_called()

        filtration.speed_standby(0).get()
        filtration.standby().get()
        assert filtration.is_comfort().get()

        filtration.overflow().get()
        assert filtration.is_overflow_normal().get()
        heating.wait.defer.assert_called()

        # Exit overflow_normal halts Swim
        swim.is_halt.return_value.get.return_value = False
        swim.halt.defer.reset_mock()
        filtration.standby().get()
        assert filtration.is_standby_normal().get()
        swim.halt.defer.assert_called()

    def test_wintering_lifecycle(self, mocker, filtration_actor, mocked_actors, filtration_temperature, encoder):
        filtration, frozen_time = filtration_actor
        do_delay_mock = mocker.patch.object(Filtration, "do_delay")

        filtration.wintering().get()
        assert filtration.is_wintering_waiting().get()
        assert filtration.is_wintering_waiting().get()
        mocked_actors["Heater"].wait.defer.assert_called_once_with()
        mocked_actors["Swim"].wintering.defer.assert_called_once_with()
        mocked_actors["Arduino"].cover_open.defer.assert_called_once_with()
        encoder.filtration_remaining.assert_called()
        do_delay_mock.assert_called_with(120, "do_repeat_wintering_waiting")

        # Before WINTERING_PERIOD -> stays waiting
        frozen_time.tick(delta=timedelta(seconds=Filtration.WINTERING_PERIOD // 2))
        do_delay_mock.reset_mock()
        filtration.do_repeat_wintering_waiting().get()
        assert filtration.is_wintering_waiting().get()
        do_delay_mock.assert_called_once_with(120, "do_repeat_wintering_waiting")

        # After WINTERING_PERIOD with warm air -> stays waiting
        frozen_time.tick(delta=timedelta(seconds=Filtration.WINTERING_PERIOD))
        filtration_temperature.temps["temperature_air"] = Filtration.WINTERING_ONLY_BELOW + 2.0
        do_delay_mock.reset_mock()
        filtration.do_repeat_wintering_waiting().get()
        assert filtration.is_wintering_waiting().get()
        do_delay_mock.assert_called_once_with(120, "do_repeat_wintering_waiting")

        # Cold air -> wintering_stir
        filtration_temperature.temps["temperature_air"] = Filtration.WINTERING_ONLY_BELOW
        do_delay_mock.reset_mock()
        filtration.do_repeat_wintering_waiting().get()
        assert filtration.is_wintering_stir().get()
        do_delay_mock.assert_called_once_with(Filtration.WINTERING_DURATION, "wintering_waiting")

        # Return to waiting and test None temperature also triggers stir
        filtration.wintering_waiting().get()
        assert filtration.is_wintering_waiting().get()
        assert filtration.is_wintering_waiting().get()
        frozen_time.tick(delta=timedelta(seconds=Filtration.WINTERING_PERIOD + 1))
        filtration_temperature.temps["temperature_air"] = None
        filtration.do_repeat_wintering_waiting().get()
        assert filtration.is_wintering_stir().get()

        # Halt exits wintering and halts Heater and Swim
        mocked_actors["Heater"].is_halt.return_value.get.return_value = False
        mocked_actors["Swim"].is_halt.return_value.get.return_value = False
        filtration.halt().get()
        assert filtration.is_halt().get()
        mocked_actors["Heater"].halt.defer.assert_called()
        mocked_actors["Swim"].halt.defer.assert_called()
