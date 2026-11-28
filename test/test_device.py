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

from unittest.mock import DEFAULT, PropertyMock, call

import pytest
import serial

from controller.device import (
    ArduinoDevice,
    DeviceRegistry,
    EZOSensorDevice,
    LcdDevice,
    PumpDevice,
    SensorDevice,
    StoppableDevice,
    SwimPumpDevice,
    SwitchDevice,
    TankSensorDevice,
    TempSensorDevice,
)


@pytest.fixture
def gpio(mocker):
    return mocker.Mock()


@pytest.fixture
def dac(mocker):
    return mocker.Mock()


PIN = 11


@pytest.fixture
def swim_pump_device(gpio, dac):
    return SwimPumpDevice("swim", gpio, PIN, dac)


@pytest.fixture
def swim_pump_device_without_dac(gpio, dac):
    type(dac).value = PropertyMock(side_effect=OSError())
    return SwimPumpDevice("swim", gpio, PIN, dac)


class TestSwimPumpDevice:
    def test_name(self, swim_pump_device):
        assert swim_pump_device.name == "swim"

    def test_on(self, gpio, dac, swim_pump_device):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        swim_pump_device.on()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        normalized_value.assert_called_once_with(1)

    def test_off(self, gpio, dac, swim_pump_device):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        swim_pump_device.off()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, True)])
        normalized_value.assert_called_once_with(0)

    def test_on_without_dac(self, gpio, swim_pump_device_without_dac):
        swim_pump_device_without_dac.on()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])

    def test_off_without_dac(self, gpio, swim_pump_device_without_dac):
        swim_pump_device_without_dac.off()
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, True)])

    @pytest.mark.parametrize("speed", range(0, 101, 25))
    def test_valid_speed(self, gpio, dac, swim_pump_device, speed):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        swim_pump_device.speed(speed)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, speed == 0)])
        normalized_value.assert_called_once_with(speed / 100)

    @pytest.mark.parametrize("speed", [-1, 101, 999])
    def test_invalid_speed(self, swim_pump_device, speed):
        with pytest.raises(AssertionError):
            swim_pump_device.speed(speed)

    def test_same_speed_one_call(self, gpio, dac, swim_pump_device):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        for _ in range(10):
            swim_pump_device.speed(50)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        normalized_value.assert_called_once_with(0.5)

    def test_change_nonzero_speed(self, gpio, dac, swim_pump_device):
        normalized_value = PropertyMock()
        type(dac).normalized_value = normalized_value
        swim_pump_device.speed(50)
        swim_pump_device.speed(75)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        assert gpio.output.call_count == 2
        normalized_value.assert_has_calls([call(0.5), call(0.75)])

    def test_dac_throws_always(self, mocker, gpio, dac, swim_pump_device):
        mocker.patch("controller.device.time.sleep")
        normalized_value = PropertyMock()
        normalized_value.side_effect = OSError()
        type(dac).normalized_value = normalized_value
        swim_pump_device.speed(50)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        normalized_value.assert_called_with(0.5)
        assert normalized_value.call_count == 3

    def test_dac_throws_once(self, mocker, gpio, dac, swim_pump_device):
        mocker.patch("controller.device.time.sleep")
        normalized_value = PropertyMock(side_effect=[OSError, DEFAULT])
        type(dac).normalized_value = normalized_value
        swim_pump_device.speed(50)
        gpio.output.assert_has_calls([call(PIN, True), call(PIN, False)])
        normalized_value.assert_called_with(0.5)
        assert normalized_value.call_count == 2


class TestDeviceRegistry:
    def test_register_and_lookup_all_categories(self, mocker, gpio):
        registry = DeviceRegistry()

        valve = SwitchDevice("gravity", gpio, 22)
        registry.add_valve(valve)
        assert registry.get_valve("gravity") is valve
        assert list(registry.get_valves()) == [valve]

        pump = PumpDevice("variable", gpio, [26, 21, 20, 16])
        boost = SwitchDevice("boost", gpio, 4)
        registry.add_pump(pump)
        registry.add_pump(boost)
        assert registry.get_pump("variable") is pump
        assert registry.get_pump("boost") is boost
        assert list(registry.get_pumps()) == [pump, boost]

        sensor = mocker.Mock(SensorDevice)
        type(sensor).name = PropertyMock(return_value="pool")
        registry.add_sensor(sensor)
        assert registry.get_sensor("pool") is sensor
        assert list(registry.get_sensors()) == [sensor]

        device = mocker.Mock(StoppableDevice)
        type(device).name = PropertyMock(return_value="arduino")
        registry.add_device(device)
        assert registry.get_device("arduino") is device
        assert list(registry.get_devices()) == [device]

    def test_add_device_rejects_wrong_type(self, mocker):
        registry = DeviceRegistry()
        other = mocker.Mock()
        with pytest.raises(AssertionError):
            registry.add_valve(other)
        with pytest.raises(AssertionError):
            registry.add_pump(other)
        with pytest.raises(AssertionError):
            registry.add_sensor(other)
        with pytest.raises(AssertionError):
            registry.add_device(other)


class TestPumpDevice:
    def test_init_requires_four_pins(self, gpio):
        with pytest.raises(AssertionError):
            PumpDevice("variable", gpio, [1, 2, 3])

    def test_on_off_and_speeds(self, gpio):
        pins = [26, 21, 20, 16]
        pump = PumpDevice("variable", gpio, pins)
        gpio.setup.assert_called_once_with(pins, gpio.OUT)
        gpio.output.assert_called_once_with(pins, True)

        gpio.output.reset_mock()
        pump.on()
        gpio.output.assert_called_once_with(pins, [True, True, True, False])

        gpio.output.reset_mock()
        pump.off()
        gpio.output.assert_called_once_with(pins, [False, True, True, True])

        gpio.output.reset_mock()
        pump.speed(2)
        gpio.output.assert_called_once_with(pins, [True, True, False, True])

        with pytest.raises(AssertionError):
            pump.speed(-1)
        with pytest.raises(AssertionError):
            pump.speed(4)


class TestTempSensorDevice:
    def test_valid_and_negative_with_offset(self, mocker):
        mocker.patch("controller.device.time.sleep")
        content = "70 01 4b 46 7f ff 0c 10 8b : crc=8b YES\n70 01 4b 46 7f ff 0c 10 8b t=23500\n"
        mocker.patch("builtins.open", mocker.mock_open(read_data=content))
        sensor = TempSensorDevice("pool", "28-0001", offset=-0.5)
        assert sensor.value == pytest.approx(23.0)

        neg_content = "ff ff 4b 46 7f ff 0c 10 8b : crc=8b YES\nff ff 4b 46 7f ff 0c 10 8b t=-5250\n"
        mocker.patch("builtins.open", mocker.mock_open(read_data=neg_content))
        sensor_no_offset = TempSensorDevice("air", "28-0002")
        assert sensor_no_offset.value == pytest.approx(-5.25)

    def test_retry_then_succeed(self, mocker):
        mocker.patch("controller.device.time.sleep")
        bad_crc = "70 01 4b 46 7f ff 0c 10 8b : crc=8b NO\n70 01 4b 46 7f ff 0c 10 8b t=23500\n"
        good = "70 01 4b 46 7f ff 0c 10 8b : crc=8b YES\n70 01 4b 46 7f ff 0c 10 8b t=21000\n"
        m1 = mocker.mock_open(read_data=bad_crc).return_value
        m2 = mocker.mock_open(read_data=good).return_value
        mocker.patch("builtins.open", side_effect=[m1, m2])
        sensor = TempSensorDevice("pool", "28-0001")
        assert sensor.value == pytest.approx(21.0)

    @pytest.mark.parametrize(
        "content",
        [
            "70 01 : crc=8b YES\n70 01 t=85000\n",
            "70 01 : crc=8b YES\n70 01 t=-25000\n",
            "70 01 : crc=8b NO\n70 01 t=20000\n",
            "single_line_only\n",
            "70 01 : crc=8b YES\n70 01 missing_temp\n",
        ],
    )
    def test_invalid_readings_return_none(self, mocker, content):
        mocker.patch("controller.device.time.sleep")
        mocker.patch("builtins.open", mocker.mock_open(read_data=content))
        sensor = TempSensorDevice("pool", "28-0001")
        assert sensor.value is None

    def test_os_error_returns_none(self, mocker):
        mocker.patch("builtins.open", side_effect=OSError("missing device"))
        sensor = TempSensorDevice("pool", "28-0001")
        assert sensor.value is None


class TestTankSensorDevice:
    def test_normal_clamped_and_partial_errors(self, mocker):
        mocker.patch("controller.device.time.sleep")
        channel = mocker.Mock()
        type(channel).voltage = PropertyMock(return_value=0.75)
        sensor = TankSensorDevice("tank", channel, low=0.5, high=1.0)
        assert sensor.value == pytest.approx(50.0)

        # Clamped to 0 and 100
        type(channel).voltage = PropertyMock(return_value=0.1)
        assert sensor.value == 0
        type(channel).voltage = PropertyMock(return_value=1.5)
        assert sensor.value == 100

        # Partial OSErrors average remaining readings
        type(channel).voltage = PropertyMock(side_effect=[OSError(), 1.0] * 5)
        assert sensor.value == 100

        # All readings fail -> returns 0
        type(channel).voltage = PropertyMock(side_effect=OSError())
        assert sensor.value == 0


class TestEZOSensorDevice:
    def test_init_read_bad_response_and_reconnect(self, mocker):
        sleep_mock = mocker.patch("controller.device.time.sleep")
        serial_instance = mocker.Mock()
        mocker.patch("controller.device.serial.Serial", return_value=serial_instance)
        mocker.patch("controller.device.SerialBuffer")
        sio_instance = mocker.Mock()
        mocker.patch("controller.device.io.TextIOWrapper", return_value=sio_instance)

        # Init: i -> ?I,pH,2.12 + *OK; C,0 -> *OK; C,? -> ?C,0 + *OK
        # Read 1: R -> 7.25 + *OK
        # Read 2: R -> *ER (bad response)
        sio_instance.readline.side_effect = [
            "?I,pH,2.12\r\n",
            "*OK\r\n",
            "*OK\r\n",
            "?C,0\r\n",
            "*OK\r\n",
            "7.25\r\n",
            "*OK\r\n",
            "*ER\r\n",
        ]
        sensor = EZOSensorDevice("ph", "/dev/ezo_ph")
        assert sensor.value == pytest.approx(7.25)
        assert sensor.value is None

        # Exception triggers reconnect
        sio_instance.write.side_effect = OSError("serial error")
        assert sensor.value is None
        serial_instance.close.assert_called_once_with()
        sleep_mock.assert_called_once_with(5)
        serial_instance.open.assert_called_once_with()

    def test_init_warns_when_continuous_not_disabled(self, mocker):
        mocker.patch("controller.device.serial.Serial")
        mocker.patch("controller.device.SerialBuffer")
        sio_instance = mocker.Mock()
        mocker.patch("controller.device.io.TextIOWrapper", return_value=sio_instance)
        sio_instance.readline.side_effect = [
            "?I,ORP,2.0\r\n",
            "*OK\r\n",
            "*OK\r\n",
            "?C,1\r\n",
            "*OK\r\n",
        ]
        EZOSensorDevice("orp", "/dev/ezo_orp")


class TestArduinoDevice:
    def test_commands_and_error_recovery(self, mocker):
        sleep_mock = mocker.patch("controller.device.time.sleep")
        check_call_mock = mocker.patch("controller.device.subprocess.check_call")
        serial_instance = mocker.Mock()
        mocker.patch("controller.device.serial.Serial", return_value=serial_instance)
        mocker.patch("controller.device.SerialBuffer")
        sio_instance = mocker.Mock()
        mocker.patch("controller.device.io.TextIOWrapper", return_value=sio_instance)

        arduino = ArduinoDevice("arduino", "/dev/arduino")
        check_call_mock.assert_called_once_with(["stty", "-F", "/dev/arduino", "-hupcl"])

        # cover_position with unexpected buffer line flushed first
        sio_instance.readline.side_effect = ["emergency stop\n", "", "position 42\n", "***\n"]
        assert arduino.cover_position == 42

        # cover_open / cover_close / cover_stop / stop
        sio_instance.readline.side_effect = ["", "open\n", "***\n"]
        arduino.cover_open()
        sio_instance.write.assert_called_with("open\n")

        sio_instance.readline.side_effect = ["", "close\n", "***\n"]
        arduino.cover_close()
        sio_instance.write.assert_called_with("close\n")

        sio_instance.readline.side_effect = ["", "stop\n", "***\n"]
        arduino.stop()
        sio_instance.write.assert_called_with("stop\n")

        # water_counter valid and bad response
        sio_instance.readline.side_effect = ["", "water 999\n", "***\n"]
        assert arduino.water_counter == 999

        sio_instance.readline.side_effect = ["", *["noise\n"] * 21]
        assert arduino.water_counter is None

        # Exception triggers reconnect
        sio_instance.readline.side_effect = serial.SerialException("disconnected")
        assert arduino.cover_position is None
        serial_instance.close.assert_called_once_with()
        sleep_mock.assert_called_once_with(5)
        serial_instance.open.assert_called_once_with()


class TestLcdDevice:
    def test_delegation_and_stop(self, mocker):
        backpack_cls = mocker.patch("lcdbackpack.LcdBackpack")
        lcd = LcdDevice("lcd", "/dev/lcd")
        backpack_cls.assert_called_once_with("/dev/lcd", 115200)
        lcd.stop()
        lcd.clear()
        backpack_cls.return_value.clear.assert_called_once_with()
