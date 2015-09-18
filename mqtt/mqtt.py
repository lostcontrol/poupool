import asyncio
from hbmqtt.client import MQTTClient

class Mqtt(object):

    def __init__(self, sensor):
        self.__sensor = sensor
                
    @asyncio.coroutine
    def main(self):
        client = MQTTClient()
        yield from client.connect('mqtt://localhost:1883/')
        yield from client.subscribe([{'filter': '/pressure', 'qos': 0x00}])
        while True:
            packet = yield from client.deliver_message()
            print("%s : %s" % (packet.variable_header.topic_name, str(packet.payload.data)))
            try:
                yield from self.__sensor.setValue(float(packet.payload.data))
            except Exception as exception:
                print("Error: %s" % exception)
            yield from client.acknowledge_delivery(packet.variable_header.packet_id)
        yield from client.unsubscribe(['/pressure'])
        yield from client.disconnect()

