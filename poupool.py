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

import os
import time
import pykka
import logging
import logging.config
import argparse
import itertools
import signal
import sys

from controller.arduino import Arduino
from controller.filtration import Filtration
from controller.disinfection import Disinfection
from controller.heating import Heating, Heater
from controller.light import Light
from controller.tank import Tank
from controller.swim import Swim
from controller.dispatcher import Dispatcher
from controller.encoder import Encoder
from controller.mqtt import Mqtt
from controller.temperature import Temperature
from controller.device import DeviceRegistry
from controller.config import config, as_list


def setup_gpio(registry, gpio):
    from controller.device import SwitchDevice, PumpDevice

    def create(device, name):
        pins = as_list(config["pins", name])
        return device(name, gpio, pins if len(pins) > 1 else pins[0])

    gpio.setmode(gpio.BCM)

    registry.add_pump(create(PumpDevice, "variable"))
    registry.add_pump(create(SwitchDevice, "boost"))

    registry.add_pump(create(SwitchDevice, "ph"))
    registry.add_pump(create(SwitchDevice, "cl"))

    registry.add_valve(create(SwitchDevice, "gravity"))
    registry.add_valve(create(SwitchDevice, "backwash"))
    registry.add_valve(create(SwitchDevice, "tank"))
    registry.add_valve(create(SwitchDevice, "drain"))
    registry.add_valve(create(SwitchDevice, "main"))

    registry.add_valve(create(SwitchDevice, "heating"))

    registry.add_valve(create(SwitchDevice, "light"))


def setup_rpi(registry):
    from controller.device import SwimPumpDevice, TempSensorDevice, TankSensorDevice, ArduinoDevice, EZOSensorDevice

    # Relay
    import RPi.GPIO as GPIO
    setup_gpio(registry, GPIO)

    # Initialize I2C bus.
    import board
    import busio
    i2c = busio.I2C(board.SCL, board.SDA)

    # ADC
    import adafruit_ads1x15.ads1015 as ADS
    # Create the ADC object using the I2C bus
    adc = ADS.ADS1015(i2c)
    # With a gain of 2/3 and a sensor output of 0.25V-5V, the values should be around 83 and 1665
    params = ((int, "channel"), (float, "gain"), (int, "low"), (int, "high"))
    registry.add_sensor(TankSensorDevice("tank", adc, *[t(config["adc", n]) for t, n in params]))

    # DAC
    import adafruit_mcp4725
    dac = adafruit_mcp4725.MCP4725(i2c)
    registry.add_pump(SwimPumpDevice("swim", GPIO, int(config["pins", "swim"]), dac))

    # pH, ORP
    registry.add_sensor(EZOSensorDevice("ph", config["serial", "ph"]))
    registry.add_sensor(EZOSensorDevice("orp", config["serial", "orp"]))

    # Arduino (cover, water)
    registry.add_device(ArduinoDevice("arduino", config["serial", "arduino"]))

    # 1-wire
    # 28-031634d04aff
    # 28-0416350909ff
    # 28-031634d54bff
    # 28-041635088bff
    registry.add_sensor(TempSensorDevice("temperature_pool", config["1-wire", "pool"]))
    registry.add_sensor(TempSensorDevice("temperature_air", config["1-wire", "air"]))
    registry.add_sensor(TempSensorDevice("temperature_local", config["1-wire", "local"]))
    registry.add_sensor(TempSensorDevice("temperature_ncc", config["1-wire", "ncc"]))


def setup_fake(registry):
    from controller.device import Device, SensorDevice, SwimPumpDevice, StoppableDevice

    class FakeGpio(object):
        OUT = "OUT"
        BCM = "BCM"

        def setmode(self, mode):
            print("Set mode to %s" % mode)

        def setup(self, pins, pins_type):
            print("Setup pin(s) %s to %s" % (str(pins), pins_type))

        def output(self, pins, values):
            print("Set pin(s) %s to %s" % (str(pins), str(values)))

    class FakeSensor(SensorDevice):
        def __init__(self, name, value):
            super().__init__(name)
            self.__value = value

        @property
        def value(self):
            return self.__value

    class FakeRandomSensor(SensorDevice):
        def __init__(self, name, min, max):
            super().__init__(name)
            self.__min = min
            self.__max = max

        @property
        def value(self):
            import random
            return random.uniform(self.__min, self.__max)

    class FakeArduino(StoppableDevice):

        def __init__(self, name):
            super().__init__(name)
            self.__cover_position = 0
            self.__cover_direction = 0
            self.__water_counter = 0

        @property
        def cover_position(self):
            if self.__cover_direction == 1:
                self.__cover_position += 40
            elif self.__cover_direction == -1:
                self.__cover_position -= 40
            self.__cover_position = min(max(self.__cover_position, 0), 100)
            return self.__cover_position

        def cover_open(self):
            self.__cover_direction = 1

        def cover_close(self):
            self.__cover_direction = -1

        def cover_stop(self):
            self.__cover_direction = 0

        @property
        def water_counter(self):
            self.__water_counter += 1
            return self.__water_counter

        def stop(self):
            self.cover_stop()

    class FakeDAC(object):

        def __init__(self):
            self.__value = 0

        @property
        def normalized_value(self):
            return self.__value

        @normalized_value.setter
        def normalized_value(self, value):
            self.__value = value

        @property
        def value(self):
            return self.__value

    # Relay
    GPIO = FakeGpio()
    setup_gpio(registry, GPIO)

    # ADC
    registry.add_sensor(FakeSensor("tank", 51.234))

    # DAC
    registry.add_pump(SwimPumpDevice("swim", GPIO, int(config["pins", "swim"]), FakeDAC()))

    # pH, ORP
    registry.add_sensor(FakeRandomSensor("ph", 6.5, 8))
    registry.add_sensor(FakeRandomSensor("orp", 640, 800))

    # 1-wire
    registry.add_sensor(FakeSensor("temperature_pool", 24.5))
    registry.add_sensor(FakeSensor("temperature_local", 20.6))
    registry.add_sensor(FakeSensor("temperature_air", 19.4))
    registry.add_sensor(FakeSensor("temperature_ncc", 21.3))

    # Arduino
    registry.add_device(FakeArduino("arduino"))


def toggle_test(device):
    print("Toggling %s " % device.name, end="")
    result = input("[y/N]: ")
    if result == "y":
        device.on()
        time.sleep(2)
        device.off()


def read_test(device):
    print("Read %s " % device.name, end="")
    try:
        result = int(input("[0-10000]: "))
        if 0 < result <= 10000:
            for _ in range(result):
                print(device.value)
                time.sleep(1)
    except ValueError:
        pass


def test(args, devices):
    pump = devices.get_pump("variable")
    print("Toggling %s " % pump.name, end="")
    result = input("[y/N]: ")
    if result == "y":
        for speed in reversed(range(4)):
            print("%s: speed %d" % (pump.name, speed))
            pump.speed(speed)
            time.sleep(2)
    toggle_test(devices.get_pump("boost"))
    toggle_test(devices.get_pump("swim"))
    toggle_test(devices.get_pump("ph"))
    toggle_test(devices.get_pump("cl"))

    toggle_test(devices.get_valve("gravity"))
    toggle_test(devices.get_valve("backwash"))
    toggle_test(devices.get_valve("tank"))
    toggle_test(devices.get_valve("drain"))
    toggle_test(devices.get_valve("main"))

    toggle_test(devices.get_valve("light"))

    # toggle_test(devices.get_valve("heater"))
    toggle_test(devices.get_valve("heating"))

    read_test(devices.get_sensor("temperature_pool"))
    read_test(devices.get_sensor("temperature_local"))
    read_test(devices.get_sensor("temperature_air"))
    read_test(devices.get_sensor("temperature_ncc"))
    read_test(devices.get_sensor("tank"))
    read_test(devices.get_sensor("ph"))
    read_test(devices.get_sensor("orp"))


# Main running flag
running = True


def main(args, devices):
    dispatcher = Dispatcher()

    mqtt = Mqtt.start(dispatcher).proxy()
    encoder = Encoder(mqtt)

    sensors = [devices.get_sensor("temperature_pool"), devices.get_sensor("temperature_local"),
               devices.get_sensor("temperature_air"), devices.get_sensor("temperature_ncc")]
    temperature = Temperature.start(encoder, sensors).proxy()
    temperature.do_read()

    filtration = Filtration.start(temperature, encoder, devices).proxy()
    swim = Swim.start(temperature, encoder, devices).proxy()
    tank = Tank.start(encoder, devices).proxy()
    disinfection = Disinfection.start(encoder, devices, args.no_disinfection).proxy()

    switch = devices.get_valve("heater")
    heater = Heater.start(temperature, switch).proxy()
    heating = Heating.start(temperature, encoder, devices).proxy()

    light = Light.start(encoder, devices).proxy()

    arduino = Arduino.start(encoder, devices).proxy()

    dispatcher.register(filtration, tank, swim, light, heater, heating, disinfection)

    mqtt.do_start()

    # Wait forever or until SIGTERM is caught
    while running:
        time.sleep(1)


def sigterm_handler(signo, stack_frame):
    global running
    running = False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-config", action="store",
                        default="logging.conf", help="log configuration file")
    parser.add_argument("--no-disinfection", action="store_true",
                        help="disable disinfection support")
    parser.add_argument("--test-mode", action="store_true", help="test mode for the hardware")
    parser.add_argument("--fake-devices", action="store_true", help="fake the underlying hardware")
    args = parser.parse_args()

    # Setup logging
    if os.path.isfile(args.log_config):
        logging.config.fileConfig(args.log_config, disable_existing_loggers=False)
    else:
        logging.error("Log configuration file (%s) cannot be used" % args.log_config)

    # Handle SIGTERM nicely. It is used by systemd to stop us.
    signal.signal(signal.SIGTERM, sigterm_handler)

    devices = DeviceRegistry()
    try:
        if args.fake_devices:
            setup_fake(devices)
        else:
            setup_rpi(devices)
        if args.test_mode:
            test(args, devices)
        else:
            main(args, devices)
    except KeyboardInterrupt:
        pass
    finally:
        pykka.ActorRegistry.stop_all()
        # Turn off all the devices on exit
        for device in itertools.chain(devices.get_pumps(), devices.get_valves()):
            device.off()
        # Stop stoppable devices
        for device in devices.get_devices():
            device.stop()
        # Ensure all the pins are configured back as inputs
        if not args.fake_devices:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
