import asyncio
import logging
from hbmqtt.client import MQTTClient

log = logging.getLogger("poupool.%s" % __name__)

class Mqtt(object):

    def __init__(self):
        self.__registry = {}

    def register(self, topic, function, type):
        self.__registry[topic] = (function, type)        

    def update(self, topic, value):
        function, type = self.__registry[topic]
        function(type(value))

    @asyncio.coroutine
    def main(self):
        client = MQTTClient()
        yield from client.connect('mqtt://localhost:1883/')
        for key in self.__registry.keys():
            yield from client.subscribe([{'filter': key, 'qos': 0x00}])
        while True:
            packet = yield from client.deliver_message()
            log.debug("%s : %s" % (packet.variable_header.topic_name, str(packet.payload.data)))
            try:
                #yield from self.getSensor("pressure-main").setValue(float(packet.payload.data))
                self.update(packet.variable_header.topic_name, packet.payload.data)
            except Exception as exception:
                log.exception(exception)
            yield from client.acknowledge_delivery(packet.variable_header.packet_id)
        for key in self.__registry.keys():
            yield from client.unsubscribe([key])
        yield from client.disconnect()

