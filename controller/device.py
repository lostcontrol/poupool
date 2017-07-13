import transitions
import time
import logging
try:
    import RPi.GPIO as GPIO
except RuntimeError:
    from unittest.mock import MagicMock
    GPIO = MagicMock()

logger = logging.getLogger("device")


class DeviceRegistry(object):

    def __init__(self):
        self.__valves = {}
        self.__pumps = {}
        self.__sensors = {}

    def add_valve(self, device):
        self.__valves[device.name] = device

    def add_pump(self, device):
        self.__pumps[device.name] = device

    def add_sensor(self, device):
        self.__sensors[device.name] = device

    def get_valve(self, name):
        return self.__valves[name]

    def get_pump(self, name):
        return self.__pumps[name]

    def get_sensor(self, name):
        return self.__sensors[name]


class Device(object):

    def __init__(self, name):
        self.name = name


class SwitchDevice(Device):

    def __init__(self, name, pin):
        super(SwitchDevice, self).__init__(name)
        self.pin = pin
        GPIO.setup(self.pin, GPIO.OUT)

    def on(self):
        GPIO.output(self.pin, True)

    def off(self):
        GPIO.output(self.pin, False)


class PumpDevice(Device):

    def __init__(self, name, pins):
        super(PumpDevice, self).__init__(name)
        assert len(pins) == 4
        self.pins = pins
        GPIO.setup(self.pins, GPIO.OUT)

    def on(self):
        self.speed(3)

    def off(self):
        self.speed(0)

    def speed(self, value):
        assert 0 <= value <= 3
        print("pump=%d" % value)
        for i, pin in enumerate(self.pins):
            GPIO.output(pin, True if pin == value else False)


class SensorDevice(Device):

    def __init__(self, name):
        super(SensorDevice, self).__init__(name)

    @property
    def value(self):
        return 50
