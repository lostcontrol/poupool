import transitions
import time
import logging
import re
from abc import abstractmethod
from .util import mapping, constrain


logger = logging.getLogger(__name__)


class DeviceRegistry(object):

    def __init__(self):
        self.__valves = {}
        self.__pumps = {}
        self.__sensors = {}

    def get_valves(self):
        return self.__valves.values()

    def get_pumps(self):
        return self.__pumps.values()

    def get_sensors(self):
        return self.__sensors.values()

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
        self.__gpio.output(self.pin, True)

    def on(self):
        logger.debug("Switch %s (%d) set to ON" % (self.name, self.pin))
        self.__gpio.output(self.pin, False)

    def off(self):
        logger.debug("Switch %s (%d) set to OFF" % (self.name, self.pin))
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
        logger.debug("Pump %s speed %d (%s:%s)" % (self.name, value, str(self.pins), str(values)))
        self.__gpio.output(self.pins, values)


class SensorDevice(Device):

    def __init__(self, name):
        super().__init__(name)

    @property
    @abstractmethod
    def value(self):
        pass


class TempSensorDevice(SensorDevice):

    CRE = re.compile(" t=(\d+)$")

    def __init__(self, name, address, offset=0.0):
        super().__init__(name)
        self.__address = address
        self.__path = "/sys/bus/w1/devices/%s/w1_slave" % address
        self.__offset = offset

    def __read_temp_raw(self):
        with open(self.__path, "r") as f:
            return [line.strip() for line in f.readlines()]

    @property
    def value(self):
        data = None
        # Retry up to 3 times
        try:
            for _ in range(3):
                raw = self.__read_temp_raw()
                if len(raw) == 2:
                    crc, data = raw
                    if crc.endswith("YES"):
                        break
                    else:
                        logger.debug("Bad CRC: %s" % str(raw))
                time.sleep(0.1)
            else:
                return None
        except OSError:
            logger.exception("Unable to read temperature (%s)" % self.name)
            return None
        logger.debug("Temp sensor raw data: %s" % str(data))
        # CRC valid, read the data
        match = TempSensorDevice.CRE.search(data)
        return int(match.group(1)) / 1000. + self.__offset if match else None


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
        logger.debug("Tank sensor average ADC=%.2f" % value)
        return constrain(mapping(value, self.__low, self.__high, 0, 100), 0, 100)
