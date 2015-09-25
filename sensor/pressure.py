import asyncio
import time

class PressureSensor(object):

    def __init__(self, mqtt):
        self.__value = 1.0
        self.__timestamp = 0
        self.__condition = asyncio.Condition()
        mqtt.register("/sensor/pressure", self.setValue, float)

    def getValue(self):
        if time.time() - self.__timestamp > 60:
            raise Exception("Too old value")
        return self.__value

    def setValue(self, value):
        if not isinstance(value, float):
            raise Exception("float is expected")
        self.__value = value
        self.__timestamp = time.time()

    @asyncio.coroutine
    def below(self, value):
        while self.getValue() >= value:
            yield from asyncio.sleep(1)
        return True

    @asyncio.coroutine
    def above(self, value):
        while self.getValue() <= value:
            yield from asyncio.sleep(1)
        return True
