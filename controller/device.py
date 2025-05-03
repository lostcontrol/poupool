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

import io
import logging
import re
import subprocess
import time
from abc import ABC, abstractmethod

import serial

from .util import constrain, mapping

logger = logging.getLogger(__name__)


class SensorError(Exception):
    pass


class DeviceRegistry:
    def __init__(self):
        self.__valves = {}
        self.__pumps = {}
        self.__sensors = {}
        self.__devices = {}

    def get_valves(self):
        return self.__valves.values()

    def get_pumps(self):
        return self.__pumps.values()

    def get_sensors(self):
        return self.__sensors.values()

    def get_devices(self):
        return self.__devices.values()

    def add_valve(self, device):
        assert isinstance(device, SwitchDevice)
        self.__valves[device.name] = device

    def add_pump(self, device):
        assert isinstance(device, SwitchDevice | PumpDevice)
        self.__pumps[device.name] = device

    def add_sensor(self, device):
        assert isinstance(device, SensorDevice)
        self.__sensors[device.name] = device

    def add_device(self, device):
        assert isinstance(device, StoppableDevice)
        self.__devices[device.name] = device

    def get_valve(self, name):
        return self.__valves.get(name)

    def get_pump(self, name):
        return self.__pumps.get(name)

    def get_sensor(self, name):
        return self.__sensors.get(name)

    def get_device(self, name):
        return self.__devices.get(name)


class Device:
    def __init__(self, name):
        self.name = name


class StoppableDevice(ABC, Device):
    def __init__(self, name):
        super().__init__(name)

    @abstractmethod
    def stop(self):
        pass


class SwitchDevice(Device):
    def __init__(self, name, gpio, pin):
        super().__init__(name)
        self.__gpio = gpio
        self.pin = pin
        self.__gpio.setup(self.pin, self.__gpio.OUT)
        self.__gpio.output(self.pin, True)

    def on(self):
        logger.debug(f"Switch {self.name} ({self.pin}) set to ON")
        self.__gpio.output(self.pin, False)

    def off(self):
        logger.debug(f"Switch {self.name} ({self.pin}) set to OFF")
        self.__gpio.output(self.pin, True)


class PumpDevice(Device):
    def __init__(self, name, gpio, pins):
        super().__init__(name)
        self.__gpio = gpio
        assert len(pins) == 4
        self.pins = pins
        self.__gpio.setup(self.pins, self.__gpio.OUT)
        self.__gpio.output(self.pins, True)

    def on(self):
        self.speed(3)

    def off(self):
        self.speed(0)

    def speed(self, value):
        assert 0 <= value <= 3
        values = [i != value for i in range(len(self.pins))]
        logger.debug(f"Pump {self.name} speed {value} ({self.pins}:{values})")
        self.__gpio.output(self.pins, values)


class SwimPumpDevice(SwitchDevice):
    def __init__(self, name, gpio, pins, dac):
        super().__init__(name, gpio, pins)
        self.__speed = -1
        # Try to write a value to the DAC. If it fails, we conclude that the DAC is not present.
        try:
            dac.value = 0
            self.__dac = dac
        except OSError:
            logger.exception("No DAC available, ignoring")
            self.__dac = None

    def on(self):
        self.speed(100)

    def off(self):
        self.speed(0)

    def speed(self, value):
        assert 0 <= value <= 100
        if self.__speed == value:
            return
        if self.__speed <= 0 and value > 0:
            super().on()
        elif self.__speed != 0 and value == 0:
            super().off()
        for _ in range(3):
            try:
                if self.__dac is not None:
                    self.__dac.normalized_value = value / 100.0
                self.__speed = value
                logger.debug(f"Swim pump {self.name} speed {value}")
                return
            except OSError:
                logger.exception(f"Unable to set {self.name} pump speed")
                time.sleep(0.2)


class SensorDevice(ABC, Device):
    def __init__(self, name):
        super().__init__(name)

    @property
    @abstractmethod
    def value(self):
        pass


class TempSensorDevice(SensorDevice):
    CRE = re.compile(r" t=(-?\d+)$")

    def __init__(self, name, address, offset=0.0):
        super().__init__(name)
        self.__address = address
        self.__path = f"/sys/bus/w1/devices/{address}/w1_slave"
        self.__offset = offset

    def __read_temp_raw(self):
        with open(self.__path) as f:
            return [line.strip() for line in f.readlines()]

    @property
    def value(self):
        # Retry up to 3 times
        try:
            for _ in range(3):
                raw = self.__read_temp_raw()
                if len(raw) == 2:
                    crc, data = raw
                    if crc.endswith("YES"):
                        logger.debug(f"Temp sensor raw data: {data!s}")
                        # CRC valid, read the data
                        match = TempSensorDevice.CRE.search(data)
                        temperature = int(match.group(1)) / 1000.0 + self.__offset if match else None
                        # Range check, sometimes bad values pass the CRC check
                        if -20 < temperature < 80:
                            return temperature
                        logger.debug(f"Temp outside range: {temperature:f}")
                    else:
                        logger.debug(f"Bad CRC: {raw!s}")
                time.sleep(0.1)
        except OSError:
            logger.exception(f"Unable to read temperature ({self.name})")
        return None


class TankSensorDevice(SensorDevice):
    def __init__(self, name, channel, low, high):
        super().__init__(name)
        self.__channel = channel
        self.__low = low
        self.__high = high

    @property
    def value(self):
        values = []
        for _ in range(10):
            try:
                values.append(self.__channel.voltage)
                time.sleep(0.05)
            except OSError:
                logger.exception(f"Unable to read ADC {self.name}")
                time.sleep(0.5)
        # In case we got really no readings, we return 0 in order for the system to go into
        # emergency stop.
        value = sum(values) / len(values) if values else 0
        logger.debug(f"Tank sensor average ADC voltage={value:.2f}")
        return constrain(mapping(value, self.__low, self.__high, 0, 100), 0, 100)


class EZOSensorDevice(SensorDevice):
    def __init__(self, name, port):
        super().__init__(name)
        self.__serial = serial.Serial(port, timeout=0.1)
        self.__sio = io.TextIOWrapper(io.BufferedRWPair(self.__serial, self.__serial))
        info = self.__send("i")
        logger.info(f"EZO sensor {name} says: {info}")
        # Disable continuous mode
        self.__send("C,0")
        if self.__send("C,?") == "?C,0":
            logger.debug("Disabled continuous readings")
        else:
            logger.error(f"Unable to disable continuous readings for {name}")

    def __reconnect(self):
        self.__serial.close()
        time.sleep(5)
        self.__serial.open()

    @property
    def value(self):
        # This can block for up to ~1000ms
        value = self.__send("R")
        return float(value) if value else None

    def __send(self, value):
        try:
            # send
            self.__sio.write(value + "\r")
            self.__sio.flush()
            # receive
            response = None
            read = self.__sio.readline()
            while not read.startswith("*"):
                # Only keep the last line of the response
                response = read.strip()
                read = self.__sio.readline()
            if read.strip() == "*OK":
                return response
            logger.error(f"Bad response: {read.strip()}")
        except Exception:
            # We catch everything in the hope that we recover with a reconnect.
            logger.exception(f"Serial sensor {self.name} had an error. Reconnecting...")
            self.__reconnect()
        return None


class ArduinoDevice(StoppableDevice):
    def __init__(self, name, port):
        super().__init__(name)
        # Disable hangup-on-close to avoid having the Arduino resetting when closing the
        # connection. Useful for debugging and to avoid interrupting a move.
        # https://playground.arduino.cc/Main/DisablingAutoResetOnSerialConnection
        subprocess.check_call(["stty", "-F", port, "-hupcl"])
        self.__serial = serial.Serial(port, baudrate=9600, timeout=0.1)
        self.__sio = io.TextIOWrapper(io.BufferedRWPair(self.__serial, self.__serial))

    def __reconnect(self):
        self.__serial.close()
        time.sleep(5)
        self.__serial.open()

    @property
    def cover_position(self):
        value = self.__send("position")
        return int(value.replace("position ", "")) if value else None

    def cover_open(self):
        self.__send("open")

    def cover_close(self):
        self.__send("close")

    def cover_stop(self):
        self.__send("stop")

    @property
    def water_counter(self):
        # self.__send_debug()
        value = self.__send("water")
        return int(value.replace("water ", "")) if value else None

    def stop(self):
        # This is to be compatible with the stoppable API. All devices are turned off() when exiting
        # the application. We stop the cover.
        self.cover_stop()

    def __send(self, value):
        try:
            # flush buffer (should be empty but we can receive an "emergency stop")
            logger.debug("Flushing read buffer")
            read = self.__sio.readline()
            while read.strip() != "":
                logger.error(f"Unexpected buffer content: {read.strip()}")
                read = self.__sio.readline()
            # send
            logger.debug(f"Writing '{value}' to serial port")
            self.__sio.write(value + "\n")
            self.__sio.flush()
            # receive
            logger.debug("Reading response")
            response = None
            counter = 0
            read = self.__sio.readline()
            while not read.startswith("***") and counter < 20:
                # Only keep the last line of the response
                response = read.strip()
                read = self.__sio.readline()
                counter += 1
            logger.debug("Received response")
            if read.strip() == "***" and response.startswith(value):
                return response
            logger.error(f"Bad response: {response} {read.strip()}")
        except Exception:
            # We catch everything in the hope that we recover with a reconnect.
            logger.exception(f"Serial sensor {self.name} had an error. Reconnecting...")
            self.__reconnect()
        return None

    def __send_debug(self):
        try:
            # flush buffer (should be empty but we can receive an "emergency stop")
            logger.debug("Flushing read buffer")
            read = self.__sio.readline()
            while read.strip() != "":
                logger.error(f"Unexpected buffer content: {read.strip()}")
                read = self.__sio.readline()
            # send
            logger.debug("Writing 'debug' to serial port")
            self.__sio.write("debug\n")
            self.__sio.flush()
            # receive
            logger.debug("Reading response")
            counter = 0
            read = self.__sio.readline()
            while not read.startswith("***") and counter < 20:
                logger.info(read.strip())
                read = self.__sio.readline()
                counter += 1
            logger.debug("Received response")
        except Exception:
            # We catch everything in the hope that we recover with a reconnect.
            logger.exception(f"Serial sensor {self.name} had an error. Reconnecting...")
            self.__reconnect()


class LcdDevice(StoppableDevice):
    def __init__(self, name, port):
        super().__init__(name)
        from lcdbackpack import LcdBackpack

        self.__lcdbackpack = LcdBackpack(port, 115200)

    def stop(self):
        pass

    def __getattr__(self, attr):
        # We just delegate everything to the LcdBackpack
        return getattr(self.__lcdbackpack, attr)
