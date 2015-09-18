import asyncio
import time

class PressureSensor(object):

    def __init__(self):
        self.__value = 1.0
        self.__timestamp = 0
        self.__condition = asyncio.Condition()

    @asyncio.coroutine
    def getValue(self):
        if time.time() - self.__timestamp > 60:
            raise Exception("Too old value")
        return self.__value

    @asyncio.coroutine
    def setValue(self, value):
        if not isinstance(value, float):
            raise Exception("float is expected")
        self.__value = value
        self.__timestamp = time.time()
        with (yield from self.__condition):
            self.__condition.notify_all()

    @asyncio.coroutine
    def below(self, value):
        while (yield from self.getValue()) >= value:
            with (yield from self.__condition):
                yield from self.__condition.wait()
