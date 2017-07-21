

class Encoder(object):

    def __init__(self, mqtt):
        self.__mqtt = mqtt

    def __getattr__(self, value):
        topic = "/status/" + "/".join(value.split("_"))
        return lambda x, **kwargs: self.__mqtt.publish(topic, x, **kwargs)
