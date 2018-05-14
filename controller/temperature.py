import logging
from .actor import PoupoolActor
from .actor import repeat

logger = logging.getLogger(__name__)


class Temperature(PoupoolActor):

    READ_DELAY = 60

    def __init__(self, encoder, sensors):
        super().__init__()
        self.__encoder = encoder
        self.__sensors = sensors
        self.__temperatures = {}

    def get_temperature(self, name):
        return self.__temperatures.get(name)

    @repeat(delay=READ_DELAY)
    def do_read(self):
        for sensor in self.__sensors:
            value = sensor.value
            # In order to avoid reading the temperature again from different actors, we cache the
            # results in a map. Other actors can then get the values from here.
            self.__temperatures[sensor.name] = value
            if value:
                rounded = round(value, 1)
                logger.debug("Temperature (%s) is %.1f°C" % (sensor.name, rounded))
                f = getattr(self.__encoder, sensor.name)
                f(rounded)
            else:
                logger.warning("Temperature (%s) cannot be read!!!" % sensor.name)
