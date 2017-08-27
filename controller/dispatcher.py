import logging

logger = logging.getLogger(__name__)


def between(minimum, maximum):
    return lambda x: minimum <= int(float(x)) <= maximum


def to_int(x):
    return int(float(x))


class Dispatcher(object):

    def __init__(self):
        self.__mapping = {}

    def register(self, filtration, swim, light):
        self.__mapping = {
            "/settings/mode": (filtration, lambda x: x in ("stop", "eco", "standby", "overflow", "wash"), lambda x: x, None),
            "/settings/filtration/duration": (filtration, between(1, 172800), lambda x: "duration", to_int),
            "/settings/filtration/hour_of_reset": (filtration, between(0, 23), lambda x: "hour_of_reset", to_int),
            "/settings/filtration/tank_duration": (filtration, between(1, 172800), lambda x: "tank_duration", to_int),
            "/settings/filtration/stir_duration": (filtration, between(0, 10 * 60), lambda x: "stir_duration", to_int),
            "/settings/filtration/backwash_period": (filtration, between(0, 90), lambda x: "backwash_period", to_int),
            "/status/filtration/backwash/last": (filtration, lambda x: True, lambda x: "backwash_last", lambda x: str(x)),
            "/settings/filtration/speed/standby": (filtration, between(0, 1), lambda x: "speed_standby", to_int),
            "/settings/filtration/speed/overflow": (filtration, between(1, 4), lambda x: "speed_overflow", to_int),
            "/settings/swim/mode": (swim, lambda x: x in ("stop", "timed", "continuous"), lambda x: x, None),
            "/settings/swim/timer": (swim, between(1, 60), lambda x: "timer", to_int),
            "/settings/light/mode": (light, lambda x: x in ("stop", "on"), lambda x: x, None),
        }

    def topics(self):
        return self.__mapping.keys()

    def dispatch(self, topic, payload):
        entry = self.__mapping.get(topic)
        if entry:
            fsm, predicate, method, value = entry
            try:
                data = payload.decode("utf-8")
                if predicate(data):
                    func = getattr(fsm, method(data))
                    param = value(data) if value else None
                    func(param) if param is not None else func()
            except Exception:
                logger.exception("Unable to process data for %s: %s" % (topic, str(payload)))
