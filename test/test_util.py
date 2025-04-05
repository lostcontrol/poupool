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

import pytest


@pytest.fixture
def util_timer():
    from controller.util import Timer

    return Timer("test")


@pytest.fixture
def util_duration():
    from controller.util import Duration

    return Duration("test")


class TestUtilDuration:
    def test_update(self, util_duration):
        util_duration.init(timedelta(seconds=100))
        assert util_duration.duration == timedelta(seconds=100)
        now = datetime.now()
        util_duration.start(now)
        util_duration.stop(now + timedelta(seconds=20))
        assert util_duration.duration == timedelta(seconds=120)

    def test_multiple_starts(self, util_duration):
        util_duration.init(timedelta(seconds=100))
        assert util_duration.duration == timedelta(seconds=100)
        now = datetime.now()
        util_duration.start(now)
        util_duration.stop(now + timedelta(seconds=20))
        assert util_duration.duration == timedelta(seconds=120)
        util_duration.start(now + timedelta(seconds=60))
        util_duration.stop(now + timedelta(seconds=80))
        assert util_duration.duration == timedelta(seconds=140)

    def test_callback(self, mocker, util_duration):
        callback_mock = mocker.Mock()
        util_duration.set_callback(callback_mock)
        util_duration.init(timedelta(seconds=30))
        assert util_duration.duration == timedelta(seconds=30)
        now = datetime.now()
        util_duration.start(now)
        util_duration.stop(now + timedelta(seconds=10))
        callback_mock.assert_called_once_with(timedelta(seconds=40))

    def test_raise_if_negative_diff(self, util_duration):
        util_duration.init(timedelta())
        now = datetime.now()
        util_duration.start(now)
        with pytest.raises(AssertionError):
            util_duration.stop(now - timedelta(seconds=10))


class TestUtilTimer:
    def test_initial(self, util_timer):
        assert util_timer.remaining == timedelta()
        assert util_timer.duration == timedelta()
        assert util_timer.delay == timedelta()
        assert util_timer.elapsed()

    def test_delay_5s(self, util_timer):
        util_timer.delay = timedelta(seconds=5)
        assert util_timer.delay == timedelta(seconds=5)
        assert util_timer.duration == timedelta()
        assert util_timer.remaining == timedelta(seconds=5)
        assert not util_timer.elapsed()

    def test_delay_5s_duration_3s(self, util_timer):
        util_timer.delay = timedelta(seconds=5)
        assert util_timer.delay == timedelta(seconds=5)
        util_timer.duration = timedelta(seconds=3)
        assert util_timer.duration == timedelta(seconds=3)
        assert util_timer.remaining == timedelta(seconds=2)
        assert not util_timer.elapsed()

    def test_delay_5s_duration_5s(self, util_timer):
        util_timer.delay = timedelta(seconds=5)
        assert util_timer.delay == timedelta(seconds=5)
        util_timer.duration = timedelta(seconds=5)
        assert util_timer.duration == timedelta(seconds=5)
        assert util_timer.remaining == timedelta()
        assert util_timer.elapsed()

    def test_delay_5s_update(self, util_timer):
        util_timer.delay = timedelta(seconds=5)
        assert util_timer.delay == timedelta(seconds=5)
        now = datetime(2000, 1, 1)
        # Initial update
        util_timer.update(now)
        assert util_timer.duration == timedelta()
        assert util_timer.remaining == timedelta(seconds=5)
        assert not util_timer.elapsed()
        # Update 3s
        now += timedelta(seconds=3)
        util_timer.update(now)
        assert util_timer.duration == timedelta(seconds=3)
        assert util_timer.remaining == timedelta(seconds=2)
        assert not util_timer.elapsed()
        # Update 3s (we go beyond the 5s)
        now += timedelta(seconds=3)
        util_timer.update(now)
        assert util_timer.duration == timedelta(seconds=6)
        assert util_timer.remaining == timedelta()
        assert util_timer.elapsed()

    def test_reset(self, util_timer):
        util_timer.delay = timedelta(seconds=5)
        assert util_timer.delay == timedelta(seconds=5)
        util_timer.duration = timedelta(seconds=3)
        assert util_timer.duration == timedelta(seconds=3)
        assert util_timer.remaining == timedelta(seconds=2)
        assert not util_timer.elapsed()
        util_timer.reset()
        assert util_timer.delay == timedelta(seconds=5)
        assert util_timer.duration == timedelta()
        assert util_timer.remaining == timedelta(seconds=5)
        assert not util_timer.elapsed()


class TestMapping:
    @pytest.mark.parametrize(("x", "y"), [(0.0, 0.0), (0.001, 1), (0.01, 10), (0.1, 100), (1.0, 1000)])
    def test_mapping_upscale(self, x, y):
        from controller.util import mapping

        # More or less 1%
        assert mapping(x, 0, 1, 0, 1000) == pytest.approx(y, rel=0.01)

    @pytest.mark.parametrize(("x", "y"), [(-127, -50), (0, 0), (127, 50), (255, 100), (512, 200)])
    def test_mapping_byte(self, x, y):
        from controller.util import mapping

        # More or less 1%
        assert mapping(x, 0, 255, 0, 100) == pytest.approx(y, rel=0.01)

    @pytest.mark.parametrize(("x", "y"), [(-100.0, -1.0), (0.0, 0.0), (50.0, 0.5), (100.0, 1.0), (200.0, 2.0)])
    def test_mapping_float(self, x, y):
        from controller.util import mapping

        # More or less 1%
        assert mapping(x, 0, 100, 0, 1) == pytest.approx(y, rel=0.01)
