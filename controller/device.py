import transitions
import time
import logging
import re
from .util import mapping, constrain

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

    def __init__(self, name, gpio, pin):
        super().__init__(name)
        self.__gpio = gpio
        self.pin = pin
        self.__gpio.setup(self.pin, self.__gpio.OUT)

    def on(self):
        self.__gpio.output(self.pin, True)

    def off(self):
        self.__gpio.output(self.pin, False)


class PumpDevice(Device):

    def __init__(self, name, gpio, pins):
        super().__init__(name)
        self.__gpio = gpio
        assert len(pins) == 4
        self.pins = pins
        self.__gpio.setup(self.pins, self.__gpio.OUT)

    def on(self):
        self.speed(3)

    def off(self):
        self.speed(0)

    def speed(self, value):
        assert 0 <= value <= 3
        for i, pin in enumerate(self.pins):
            self.__gpio.output(pin, True if pin == value else False)


class SensorDevice(Device):

    def __init__(self, name):
        super().__init__(name)

    @property
    def value(self):
        return 50


class TempSensorDevice(SensorDevice):

    CRE = re.compile(" t=(\d+)$")

    def __init__(self, name, address):
        super().__init__(name)
        self.__address = address
        self.__path = "/sys/bus/w1/devices/%s/w1_slave" % address

    def __read_temp_raw(self):
        with open(self.__path, "r") as f:
            return f.readlines()

    @property
    def value(self):
        data = None
        # Retry up to 3 times
        for _ in range(3):
            raw = self.__read_temp_raw()
            if len(raw) == 2:
                crc, data = raw
                if crc.endswith("YES"):
                    break
            time.sleep(0.1)
        else:
            return None
        # CRC valid, read the data
        match = CRE.search(data)
        return int(match.group(1)) / 1000. if match else None


class TankSensorDevice(SensorDevice):

    def __init__(self, name, adc, channel, gain, low, high):
        super().__init__(name)
        self.__adc = adc
        self.__channel = channel
        self.__gain = gain
        self.__low = low
        self.__high = high

    @property
    def value(self):
        values = 0
        for i in range(10):
            values += self.__adc.read_adc(self.__channel, gain=self.__gain)
            time.sleep(0.05)
        value = values / 10
        return constrain(mapping(value, self.__low, self.__high, 0, 100), 0, 100)
