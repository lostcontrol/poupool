

class Dispatcher(object):

    def __init__(self):
        self.__mapping = {}

    def register(self, filtration, swim):
        self.__mapping = {
            "/settings/mode": (filtration, lambda x: x in ("stop", "eco", "standby", "overflow"), lambda x: x, None),
            "/settings/filtration/duration": (filtration, lambda x: 0 < int(x) <= 172800, lambda x: "duration", lambda x: int(x)),
            "/settings/filtration/hour_of_reset": (filtration, lambda x: 0 < int(x) <= 23, lambda x: "hour_of_reset", lambda x: int(x)),
            "/settings/filtration/tank_duration": (filtration, lambda x: 0 < int(x) <= 172800, lambda x: "tank_duration", lambda x: int(x)),
            "/settings/filtration/stir_duration": (filtration, lambda x: 0 <= int(x) <= 10 * 60, lambda x: "stir_duration", lambda x: int(x)),
            "/settings/filtration/speed/standby": (filtration, lambda x: 0 <= int(x) <= 1, lambda x: "speed_standby", lambda x: int(x)),
            "/settings/filtration/speed/overflow": (filtration, lambda x: 0 < int(x) <= 4, lambda x: "speed_overflow", lambda x: int(x)),
            "/settings/swim/mode": (swim, lambda x: x in ("stop", "timed", "continuous"), lambda x: x, None),
            "/settings/swim/timer": (swim, lambda x: 0 < int(x) <= 60, lambda x: "timer", lambda x: int(x)),
        }

    def topics(self):
        return self.__mapping.keys()

    def dispatch(self, topic, payload):
        entry = self.__mapping.get(topic)
        if entry:
            fsm, predicate, method, value = entry
            data = payload.decode("utf-8")
            if predicate(data):
                func = getattr(fsm, method(data))
                param = value(data) if value else None
                func(param) if param is not None else func()
