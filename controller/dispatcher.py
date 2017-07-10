

class Dispatcher(object):
    
    def __init__(self, filtration):
        self.__mapping = {
            "/settings/mode": (filtration, lambda x: x in ("stop", "eco", "overflow"), lambda x: x, None),
            "/settings/filtration/duration": (filtration, lambda x: 0 < int(x) <= 172800, lambda x: "duration", lambda x: int(x)),
            "/settings/filtration/hour_of_reset": (filtration, lambda x: 0 < int(x) <= 23, lambda x: "hour_of_reset", lambda x: int(x)),
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
                func(param) if param else func()
        
