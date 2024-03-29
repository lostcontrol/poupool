# Poupool - swimming pool control software
# Copyright (C) 2020 Cyril Jaquier
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

from controller.sensor import MovingAverage


@pytest.fixture()
def temperature_reader(mocker):
    from controller.sensor import TemperatureReader

    return TemperatureReader({})


class TestTemperatureReader:
    def test_slope_empty(self, mocker, temperature_reader):
        mock_values = mocker.patch("controller.sensor.TemperatureReader.values", new_callable=mocker.PropertyMock)
        mock_values.return_value = {"pool": MovingAverage(10)}
        assert temperature_reader.get_temperature_slope("pool") == 0

    def test_slope_one_value(self, mocker, temperature_reader):
        average = MovingAverage(10)
        for _ in range(1):
            average.push(20)
        mock_values = mocker.patch("controller.sensor.TemperatureReader.values", new_callable=mocker.PropertyMock)
        mock_values.return_value = {"pool": average}
        assert temperature_reader.get_temperature_slope("pool") == 0

    def test_slope_two_values(self, mocker, temperature_reader):
        average = MovingAverage(10)
        for i in range(2):
            average.push(i)
        mock_values = mocker.patch("controller.sensor.TemperatureReader.values", new_callable=mocker.PropertyMock)
        mock_values.return_value = {"pool": average}
        assert temperature_reader.get_temperature_slope("pool") == 60

    def test_slope_constant_values(self, mocker, temperature_reader):
        average = MovingAverage(10)
        for _ in range(10):
            average.push(20)
        mock_values = mocker.patch("controller.sensor.TemperatureReader.values", new_callable=mocker.PropertyMock)
        mock_values.return_value = {"pool": average}
        assert temperature_reader.get_temperature_slope("pool") == 0

    def test_slope_increasing(self, mocker, temperature_reader):
        average = MovingAverage(10)
        for i in range(10):
            average.push(i)
        mock_values = mocker.patch("controller.sensor.TemperatureReader.values", new_callable=mocker.PropertyMock)
        mock_values.return_value = {"pool": average}
        assert temperature_reader.get_temperature_slope("pool") == 60

    def test_slope_decreasing(self, mocker, temperature_reader):
        average = MovingAverage(10)
        for i in range(10, 0, -1):
            average.push(i)
        mock_values = mocker.patch("controller.sensor.TemperatureReader.values", new_callable=mocker.PropertyMock)
        mock_values.return_value = {"pool": average}
        assert temperature_reader.get_temperature_slope("pool") == -60

    def test_slope_incomplete(self, mocker, temperature_reader):
        average = MovingAverage(10)
        for i in range(5):
            average.push(i)
        mock_values = mocker.patch("controller.sensor.TemperatureReader.values", new_callable=mocker.PropertyMock)
        mock_values.return_value = {"pool": average}
        assert temperature_reader.get_temperature_slope("pool") == 60
