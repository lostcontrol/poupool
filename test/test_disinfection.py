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

import pytest
from unittest import mock


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
