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

from unittest import mock

import pytest


@pytest.fixture
def pump(mocker):
    from controller.device import SwitchDevice

    return mocker.Mock(SwitchDevice)


@pytest.fixture
def pwm(pump):
    from controller.disinfection import PWM

    return PWM("test", pump, min_runtime=0)


class TestPWM:
    @pytest.mark.parametrize("value", [round(x * 0.2, 1) for x in range(0, 6)])
    @pytest.mark.parametrize("period", [10, 60, 150])
    def test_pwm(self, period, value, pwm, pump):
        pwm.period = period
        pwm.value = value
        on_step = (1 - pwm.value) * pwm.period
        # First call is to initialize the loop
        with mock.patch("time.time", return_value=0):
            pwm.do_run()
        # The actual period
        for i in range(1, pwm.period + 1, 1):
            with mock.patch("time.time", return_value=i):
                pwm.do_run()
            if i == on_step + 1:
                pump.on.assert_called_once_with()
        # One more to see if we get the off transition
        with mock.patch("time.time", return_value=pwm.period + 2):
            pwm.do_run()
        # Only if pwm.value != 1.0 we will stop the pump at the end of the period
        if on_step not in (0, pwm.period):
            pump.off.assert_called_once_with()

    def run_many_iterations(self, pwm, iterations):
        loops = iterations * pwm.period
        # First call is to initialize the loop
        with mock.patch("time.time", return_value=0):
            pwm.do_run()
        # The actual period
        for i in range(1, loops + 1, 1):
            with mock.patch("time.time", return_value=i):
                pwm.do_run()
        # One more to see if we get the off transition
        with mock.patch("time.time", return_value=loops + 2):
            pwm.do_run()

    def test_pwm_many_iterations_0_5(self, pwm, pump):
        pwm.period = 10
        pwm.value = 0.5
        iterations = 100
        self.run_many_iterations(pwm, iterations)
        assert pump.on.call_count == iterations
        assert pump.off.call_count == iterations

    def test_pwm_many_iterations_1_0(self, pwm, pump):
        pwm.period = 10
        pwm.value = 1.0
        iterations = 100
        self.run_many_iterations(pwm, iterations)
        assert pump.on.call_count == 1
        assert pump.off.call_count == 0

    def test_pwm_many_iterations_0_0(self, pwm, pump):
        pwm.period = 10
        pwm.value = 0.0
        iterations = 100
        self.run_many_iterations(pwm, iterations)
        assert pump.on.call_count == 0
        assert pump.off.call_count == 0


class TestCanisterMonitor:
    def test_insufficient_samples_discarded(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", min_samples=15)
        for _ in range(10):
            assert not monitor.add_sample(0.50)
        assert not monitor.finish_cycle()
        assert len(monitor.history) == 0
        assert not monitor.is_empty

    def test_normal_cycles_no_alert(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", cycles=6, min_samples=15)
        # Normal fluctuating duty cycles between 1% and 4%
        normal_values = [0.01, 0.02, 0.01, 0.03, 0.02, 0.01, 0.04, 0.02, 0.01]
        for val in normal_values:
            for _ in range(20):
                monitor.add_sample(val)
            assert not monitor.finish_cycle()
            assert not monitor.is_empty

    def test_upward_trend_detection(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", cycles=6, min_samples=15)
        # 6 cycles with increasing feedback matching empty canister progression
        trend_values = [0.11, 0.15, 0.18, 0.21, 0.23, 0.26]
        for idx, val in enumerate(trend_values):
            for _ in range(20):
                monitor.add_sample(val)
            is_last = idx == len(trend_values) - 1
            changed = monitor.finish_cycle()
            if is_last:
                assert changed
                assert monitor.is_empty
                assert monitor.alert_stats is not None
                assert monitor.alert_stats.peak == pytest.approx(0.26)
            else:
                assert not changed
                assert not monitor.is_empty

    def test_saturation_fallback(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", cycles=6, min_samples=15)
        # 6 cycles with high duty cycle saturation
        high_values = [0.40, 0.50, 0.45, 0.60, 0.55, 0.50]
        for idx, val in enumerate(high_values):
            for _ in range(20):
                monitor.add_sample(val)
            is_last = idx == len(high_values) - 1
            changed = monitor.finish_cycle()
            if is_last:
                assert changed
                assert monitor.is_empty
            else:
                assert not changed
                assert not monitor.is_empty

    def test_summer_spike_recovering_at_night(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", cycles=6, min_samples=15)
        # Alternating afternoon spike and overnight low recovery
        day_night_values = [0.45, 0.02, 0.50, 0.02, 0.40, 0.02, 0.55, 0.02]
        for val in day_night_values:
            for _ in range(20):
                monitor.add_sample(val)
            assert not monitor.finish_cycle()
            assert not monitor.is_empty

    def test_auto_clear_on_low_demand(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", cycles=6, min_samples=15)
        # Trigger empty state
        for val in [0.11, 0.15, 0.18, 0.21, 0.23, 0.26]:
            for _ in range(20):
                monitor.add_sample(val)
            monitor.finish_cycle()
        assert monitor.is_empty

        # Canister refilled: low demand for 15 samples clears flag mid-cycle
        for _ in range(14):
            assert not monitor.add_sample(0.02)
            assert monitor.is_empty
        assert monitor.add_sample(0.02)
        assert not monitor.is_empty
        assert len(monitor.history) == 0

    def test_auto_clear_on_relative_drop(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", cycles=6, min_samples=15)
        # Trigger empty state at high saturation
        for val in [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
            for _ in range(20):
                monitor.add_sample(val)
            monitor.finish_cycle()
        assert monitor.is_empty

        # Next cycle drops significantly (peak 0.40, mean 0.20)
        # First 14 samples: moderate values
        for _ in range(14):
            assert not monitor.add_sample(0.20)
        # Finish cycle with 20 samples total
        for _ in range(6):
            assert not monitor.add_sample(0.20)
        assert monitor.finish_cycle()
        assert not monitor.is_empty

    def test_max_samples_auto_split(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", min_samples=15, max_samples=30)
        for _ in range(29):
            assert not monitor.add_sample(0.20)
        assert len(monitor.history) == 0
        # 30th sample triggers cycle split
        monitor.add_sample(0.20)
        assert len(monitor.history) == 1
        assert len(monitor.current_samples) == 0

    def test_restore_and_clear(self):
        from controller.disinfection import CanisterMonitor

        monitor = CanisterMonitor("Cl", min_samples=15)
        monitor.restore(True)
        assert monitor.is_empty

        # Auto-clear after 15 low samples
        for _ in range(15):
            monitor.add_sample(0.01)
        assert not monitor.is_empty

        # Restore False resets state
        monitor.restore(True)
        assert monitor.is_empty
        monitor.restore(False)
        assert not monitor.is_empty


class TestDisinfectionCanisterIntegration:
    @pytest.fixture
    def encoder(self, mocker):
        return mocker.Mock()

    @pytest.fixture
    def devices(self, mocker):
        from controller.device import DeviceRegistry, SwitchDevice

        registry = mocker.Mock(DeviceRegistry)
        pump_mock = mocker.Mock(SwitchDevice)
        registry.get_pump.return_value = pump_mock
        return registry

    @pytest.fixture
    def sensors_reader(self, mocker):
        reader = mocker.Mock()
        ph_mock = mocker.Mock()
        ph_mock.get.return_value = 7.2
        orp_mock = mocker.Mock()
        orp_mock.get.return_value = 650
        reader.get_ph.return_value = ph_mock
        reader.get_orp.return_value = orp_mock
        return reader

    @pytest.fixture
    def sensors_writer(self, mocker):
        return mocker.Mock()

    @pytest.fixture
    def disinfection(self, encoder, devices, sensors_reader, sensors_writer):
        import pykka

        from controller.disinfection import Disinfection

        yield Disinfection(encoder, devices, sensors_reader, sensors_writer, disable=True)
        pykka.ActorRegistry.stop_all()

    def test_dispatcher_restore_callbacks(self, disinfection, encoder, sensors_reader):
        # Restoring True sets empty state; subsequent low-demand samples will trigger clear publish
        encoder.reset_mock()
        disinfection.cl_canister_empty(True)
        encoder.disinfection_cl_canister__empty.assert_not_called()

        # Calling cl_canister_empty(True) again is idempotent
        disinfection.cl_canister_empty(True)
        encoder.disinfection_cl_canister__empty.assert_not_called()

        # 15 low-demand samples trigger auto-clear publish
        for _ in range(15):
            disinfection.on_enter_running_adjusting()
        encoder.disinfection_cl_canister__empty.assert_called_once_with(0, retain=True)

        # Restoring False
        encoder.reset_mock()
        disinfection.cl_canister_empty(False)
        encoder.disinfection_cl_canister__empty.assert_not_called()
        # When already False, 15 low-demand samples do not publish clear
        for _ in range(15):
            disinfection.on_enter_running_adjusting()
        encoder.disinfection_cl_canister__empty.assert_not_called()

    def test_canister_empty_published_on_transition(self, disinfection, encoder, sensors_reader):
        encoder.reset_mock()
        # Setpoint is 600, scale is 0.005, pterm is 1.0.
        # feedback = (setpoint - current) * pterm * scale = (600 - orp) * 0.005
        # ORPs: 578 (0.11), 570 (0.15), 564 (0.18)
        orps = [578, 570, 564]
        for idx, orp in enumerate(orps):
            sensors_reader.get_orp().get.return_value = orp
            for _ in range(15):
                disinfection.on_enter_running_adjusting()
            disinfection.on_enter_halt()
            if idx < len(orps) - 1:
                encoder.disinfection_cl_canister__empty.assert_not_called()
            else:
                encoder.disinfection_cl_canister__empty.assert_called_once_with(1, retain=True)
