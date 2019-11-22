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

from datetime import timedelta, datetime
from freezegun import freeze_time
import pytest
from unittest import mock


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
