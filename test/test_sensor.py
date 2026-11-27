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

from unittest.mock import PropertyMock

import pytest

from controller.device import SensorDevice
from controller.sensor import (
    DisinfectionReader,
    DisinfectionWriter,
    MovingAverage,
    TemperatureReader,
    TemperatureWriter,
)


@pytest.fixture
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

    def test_read_and_get_temperatures(self, mocker):
        mocker.patch.object(TemperatureReader, "do_delay")
        pool_sensor = mocker.Mock(SensorDevice)
        type(pool_sensor).name = PropertyMock(return_value="temperature_pool")
        type(pool_sensor).value = PropertyMock(side_effect=[20.0, 22.0, None])

        air_sensor = mocker.Mock(SensorDevice)
        type(air_sensor).name = PropertyMock(return_value="temperature_air")
        type(air_sensor).value = PropertyMock(side_effect=[None, 18.0, 19.0])

        reader = TemperatureReader.start([pool_sensor, air_sensor]).proxy()
        try:
            assert reader.get_temperature("temperature_pool").get() is None
            assert reader.get_all_temperatures().get() == {"temperature_pool": None, "temperature_air": None}

            do_delay_mock = mocker.patch.object(TemperatureReader, "do_delay")
            reader.do_read().get()
            do_delay_mock.assert_called_once_with(TemperatureReader.DELAY_SECONDS, "do_read")
            assert reader.get_temperature("temperature_pool").get() == pytest.approx(20.0)
            assert reader.get_temperature("temperature_air").get() is None

            reader.do_read().get()
            assert reader.get_temperature("temperature_pool").get() == pytest.approx(21.0)
            assert reader.get_all_temperatures().get() == {
                "temperature_pool": pytest.approx(21.0),
                "temperature_air": pytest.approx(18.0),
            }

            # None values are not pushed
            reader.do_read().get()
            assert reader.get_temperature("temperature_pool").get() == pytest.approx(21.0)
        finally:
            reader.stop().get()


class TestMovingAverage:
    def test_empty_push_maxlen_clear(self):
        avg = MovingAverage(3)
        assert avg.mean() is None
        assert avg.all() == []

        avg.push(1.0)
        avg.push(2.0)
        avg.push(3.0)
        avg.push(4.0)
        assert avg.all() == [2.0, 3.0, 4.0]
        assert avg.mean() == pytest.approx(3.0)

        avg.clear()
        assert avg.all() == []
        assert avg.mean() is None


class TestDisinfectionReaderWriter:
    def test_disinfection_reader_and_writer(self, mocker):
        mocker.patch.object(DisinfectionReader, "do_delay")
        mocker.patch.object(DisinfectionWriter, "do_delay")

        ph_sensor = mocker.Mock(SensorDevice)
        type(ph_sensor).name = PropertyMock(return_value="ph")
        type(ph_sensor).value = PropertyMock(side_effect=[None, 7.24, 7.26])

        orp_sensor = mocker.Mock(SensorDevice)
        type(orp_sensor).name = PropertyMock(return_value="orp")
        type(orp_sensor).value = PropertyMock(side_effect=[None, 650, 660])

        encoder = mocker.Mock()
        reader = DisinfectionReader.start([ph_sensor, orp_sensor]).proxy()
        writer = DisinfectionWriter.start(encoder, reader).proxy()
        try:
            # First read returns None -> writer does not publish
            reader.do_read().get()
            assert reader.get_ph().get() is None
            assert reader.get_orp().get() is None
            writer.do_write().get()
            encoder.disinfection_orp_value.assert_not_called()
            encoder.disinfection_ph_value.assert_not_called()

            # Valid reads -> writer formats and publishes
            reader.do_read().get()
            reader.do_read().get()
            assert reader.get_ph().get() == pytest.approx(7.25)
            assert reader.get_orp().get() == pytest.approx(655)

            do_delay_mock = mocker.patch.object(DisinfectionWriter, "do_delay")
            writer.do_write().get()
            encoder.disinfection_orp_value.assert_called_once_with("655")
            encoder.disinfection_ph_value.assert_called_once_with("7.25")
            do_delay_mock.assert_called_once_with(DisinfectionWriter.DELAY_SECONDS, "do_write")
        finally:
            writer.stop().get()
            reader.stop().get()


class TestTemperatureWriter:
    def test_temperature_writer(self, mocker):
        do_delay_mock = mocker.patch.object(TemperatureWriter, "do_delay")
        encoder = mocker.Mock()
        reader = mocker.Mock()
        reader.get_all_temperatures.return_value.get.return_value = {
            "temperature_pool": 25.46,
            "temperature_air": None,
        }
        reader.get_temperature_slope.return_value.get.return_value = 0.126

        writer = TemperatureWriter.start(encoder, reader).proxy()
        try:
            writer.do_write().get()
            encoder.temperature_pool.assert_called_once_with(25.5)
            encoder.temperature_air.assert_not_called()
            encoder.temperature_pool__slope.assert_called_once_with(0.13)
            do_delay_mock.assert_called_once_with(TemperatureWriter.DELAY_SECONDS, "do_write")
        finally:
            writer.stop().get()
