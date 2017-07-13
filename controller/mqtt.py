import paho.mqtt.client as mqtt

import pykka
from .actor import PoupoolActor


class Mqtt(PoupoolActor):

    def __init__(self, dispatcher):
        super(Mqtt, self).__init__()
        self.__run = True
        self.__dispatcher = dispatcher
        self.__client = mqtt.Client()
        self.__client.on_message = self.__on_message

    def __on_message(self, client, userdata, message):
        self.__dispatcher.dispatch(message.topic, message.payload)

    def do_loop(self):
        if self.__run:
            self.__client.loop(timeout=1.0)
            self._proxy.do_loop()

    def do_start(self):
        self.__client.connect("localhost")
        for topic in self.__dispatcher.topics():
            self.__client.subscribe(topic)
        self._proxy.do_loop()

    def do_stop(self):
        self.__run = False
