import os
import time
import pykka
import logging
import logging.config
import argparse
import itertools

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


def setup_gpio(registry, gpio):
    from controller.device import SwitchDevice, PumpDevice

    gpio.setmode(gpio.BOARD)

    registry.add_pump(PumpDevice("variable", gpio, [37, 40, 38, 36]))
    registry.add_pump(SwitchDevice("boost", gpio, 7))
    registry.add_pump(SwitchDevice("swim", gpio, 11))

    registry.add_pump(SwitchDevice("ph", gpio, 22))
    registry.add_pump(SwitchDevice("cl", gpio, 32))

    registry.add_valve(SwitchDevice("gravity", gpio, 15))
    registry.add_valve(SwitchDevice("backwash", gpio, 29))
    registry.add_valve(SwitchDevice("tank", gpio, 33))
    registry.add_valve(SwitchDevice("drain", gpio, 31))
    registry.add_valve(SwitchDevice("main", gpio, 35))

    #registry.add_valve(SwitchDevice("heater", gpio, 18))
    registry.add_valve(SwitchDevice("heating", gpio, 18))

    registry.add_valve(SwitchDevice("light", gpio, 13))


def setup_rpi(registry):
    from controller.device import TempSensorDevice, TankSensorDevice, ArduinoDevice, EZOSensorDevice

    # Relay
    import RPi.GPIO as GPIO
    setup_gpio(registry, GPIO)

    # ADC
    import Adafruit_ADS1x15
    adc = Adafruit_ADS1x15.ADS1015()
    # With a gain of 2/3 and a sensor output of 0.25V-5V, the values should be around 83 and 1665
    registry.add_sensor(TankSensorDevice("tank", adc, 0, 2 / 3, 83, 1665))

    from controller.device import Device, SensorDevice

    class FakeRandomSensor(SensorDevice):
        def __init__(self, name, min, max):
            super().__init__(name)
            self.__min = min
            self.__max = max

        @property
        def value(self):
            import random
            return random.uniform(self.__min, self.__max)

    class FakeArduino(Device):

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

        def off(self):
            self.cover_stop()


#     # pH, ORP
#     registry.add_sensor(EZOSensorDevice("ph", "/dev/ezo_ph"))
#     registry.add_sensor(EZOSensorDevice("orp", "/dev/ezo_orp"))
#
#     # Arduino (cover, water)
#     registry.add_valve(ArduinoDevice("arduino", "/dev/arduino"))

    # pH, ORP
    registry.add_sensor(FakeRandomSensor("ph", 6.5, 8))
    registry.add_sensor(FakeRandomSensor("orp", 640, 800))

    # Arduino
    registry.add_valve(FakeArduino("arduino"))

    # 1-wire
    # 28-031634d04aff
    # 28-0416350909ff
    # 28-031634d54bff
    # 28-041635088bff
    registry.add_sensor(TempSensorDevice("temperature_pool", "28-031634d04aff"))
    registry.add_sensor(TempSensorDevice("temperature_air", "28-0416350909ff"))
    registry.add_sensor(TempSensorDevice("temperature_local", "28-031634d54bff"))
    registry.add_sensor(TempSensorDevice("temperature_ncc", "28-041635088bff"))


def setup_fake(registry):
    from controller.device import Device, SensorDevice

    class FakeGpio(object):
        OUT = "OUT"
        BOARD = "BOARD"

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

    class FakeArduino(Device):

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

        def off(self):
            self.cover_stop()

    # Relay
    GPIO = FakeGpio()
    setup_gpio(registry, GPIO)

    # ADC
    registry.add_sensor(FakeSensor("tank", 51.234))

    # pH, ORP
    registry.add_sensor(FakeRandomSensor("ph", 6.5, 8))
    registry.add_sensor(FakeRandomSensor("orp", 640, 800))

    # 1-wire
    registry.add_sensor(FakeSensor("temperature_pool", 24.5))
    registry.add_sensor(FakeSensor("temperature_local", 20.6))
    registry.add_sensor(FakeSensor("temperature_air", 19.4))
    registry.add_sensor(FakeSensor("temperature_ncc", 21.3))

    # Arduino
    registry.add_valve(FakeArduino("arduino"))


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


def main(args, devices):
    dispatcher = Dispatcher()

    mqtt = Mqtt.start(dispatcher).proxy()
    encoder = Encoder(mqtt)

    filtration = Filtration.start(encoder, devices).proxy()
    swim = Swim.start(encoder, devices).proxy()
    tank = Tank.start(encoder, devices).proxy()
    disinfection = Disinfection.start(encoder, devices, args.no_disinfection).proxy()

    sensors = [devices.get_sensor("temperature_pool"), devices.get_sensor("temperature_local"),
               devices.get_sensor("temperature_air"), devices.get_sensor("temperature_ncc")]
    temperature = Temperature.start(encoder, sensors).proxy()
    temperature.do_read()

    switch = devices.get_valve("heater")
    heater = Heater.start(temperature, switch).proxy()
    heating = Heating.start(temperature, encoder, devices).proxy()

    light = Light.start(encoder, devices).proxy()

    arduino = Arduino.start(encoder, devices).proxy()

    dispatcher.register(filtration, swim, light, heater, heating, disinfection)

    mqtt.do_start()

    # Wait forever
    while True:
        time.sleep(1000)


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
        pykka.ActorRegistry.stop_all()
    finally:
        # Turn off all the devices on exit
        for device in itertools.chain(devices.get_pumps(), devices.get_valves()):
            device.off()
        # Ensure all the pins are configured back as inputs
        if not args.fake_devices:
            import RPi.GPIO as GPIO
            GPIO.cleanup()