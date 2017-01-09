import asyncio
import logging
from hbmqtt.client import MQTTClient

log = logging.getLogger("poupool.%s" % __name__)

class Mqtt(object):

    def __init__(self):
        self.__registry = {}

    def register(self, topic, function, type):
        self.__registry[topic] = (function, type)        

    async def update(self, topic, value):
        function, type = self.__registry[topic]
        await function(type(value))

    async def main(self):
        client = MQTTClient()
        await client.connect('mqtt://localhost:1883/')
        for key in self.__registry.keys():
            #yield from client.subscribe([{'filter': key, 'qos': 0x00}])
            await client.subscribe([(key, 0)])
        while True:
            packet = await client.deliver_message()
            log.debug("%s : %s" % (packet.topic, str(packet.data)))
            try:
                #yield from self.getSensor("pressure-main").setValue(float(packet.payload.data))
                data = packet.data.decode("utf-8")
                await self.update(packet.topic, data)
            except Exception as exception:
                log.exception(exception)
        for key in self.__registry.keys():
            await client.unsubscribe([key])
        await client.disconnect()

