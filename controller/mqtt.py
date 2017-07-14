import paho.mqtt.client as mqtt
import time
import logging
import pykka
from .actor import PoupoolActor
from .actor import StopRepeatException, repeat

logger = logging.getLogger(__name__)


class Mqtt(PoupoolActor):

    def __init__(self, dispatcher):
        super(Mqtt, self).__init__()
        self.__run = True
        self.__dispatcher = dispatcher
        self.__client = mqtt.Client()
        self.__client.on_connect = self.__on_connect
        self.__client.on_message = self.__on_message
        self.__client.on_disconnect = self.__on_disconnect

    def __on_connect(self, client, userdata, flags, rc):
        logger.info("MQTT client connected to broker")
        for topic in self.__dispatcher.topics():
            self.__client.subscribe(topic)

    def __on_message(self, client, userdata, message):
        self.__dispatcher.dispatch(message.topic, message.payload)

    def __on_disconnect(self, client, userdata, rc):
        logger.warn("MQTT client disconnected: %d" % rc)
        if rc != 0:
            self.do_connect()

    @repeat(delay=5)
    def do_connect(self):
        try:
            self.__client.connect("localhost")
        except Exception as e:
            logger.error("Unable to connect to MQTT broker: %s" % e)
        else:
            raise StopRepeatException

    def do_start(self):
        self.do_connect()
        self._proxy.do_loop()

    @repeat(delay=0)
    def do_loop(self):
        if not self.__run:
            raise StopRepeatException()
        self.__client.loop(timeout=1.0)

    def do_stop(self):
        self.__run = False

    def publish(self, topic, payload, qos=0, retain=False):
        result, mid = self.__client.publish(topic, payload, qos, retain)
        if result != 0:
            logger.error("Unable to publish topic '%s':'%s'" % (topic, str(payload)))
            return False
        return True

