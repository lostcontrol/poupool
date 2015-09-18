import asyncio

class Filtration(object):

    def __init__(self, pump, valve, pressure):
        self.__pump = pump
        self.__valve = valve
        self.__sensor = {}
        self.__sensor["pressure"] = pressure

    @asyncio.coroutine
    def backwash(self):
        print("Backwash started")
        yield from self.__pump.stop()
        yield from asyncio.sleep(1)
        yield from self.__valve.close()
        yield from asyncio.sleep(1)
        yield from self.__pump.start()
        try:
            yield from asyncio.wait_for(self.__sensor["pressure"].below(2.0), 20)
        except asyncio.TimeoutError:
            print("Washing takes too long, interrupting...")
        yield from self.__pump.stop()
        yield from asyncio.sleep(1)
        yield from self.__valve.open()
        yield from asyncio.sleep(1)
        yield from self.__pump.start()
        print("Backwash done")

    @asyncio.coroutine
    def main(self, loop):
        while True:
            try:
                if (yield from self.__sensor["pressure"].getValue()) > 3.0:
                    yield from self.backwash()
                else:
                    yield from asyncio.sleep(1)
            except Exception as exception:
                print("Error: %s" % exception)
                yield from self.__pump.stop()
                yield from asyncio.sleep(1)

