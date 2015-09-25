import asyncio
import logging
from controller.fsm import Fsm, FsmState, FsmTask

log = logging.getLogger("poupool.%s" % __name__)

class Stop(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    @asyncio.coroutine
    def run(self):
        print("Stop")
        yield from asyncio.sleep(1)

    def transition(self, event):
        if event == "economy":
            return self.get_state("economy")
        if event == "overflow":
            return self.get_state("overflow")
        return self

class Economy(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    @asyncio.coroutine
    def run(self):
        print("Economy")
        yield from asyncio.sleep(1)

    def transition(self, event):
        if event == "stop":
            return self.get_state("stop")
        if event == "overflow":
            return self.get_state("overflow")
        return self

class Overflow(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    @asyncio.coroutine
    def run(self):
        print("Overflow")
        yield from asyncio.sleep(1)

    def transition(self, event):
        if event == "stop":
            return self.get_state("stop")
        if event == "economy":
            return self.get_state("economy")
        return self


class Filtration(Fsm):

    def __init__(self, system, heating):
        super().__init__()
        self.add_state("stop", Stop(self))
        self.add_state("economy", Economy(self))
        self.add_state("overflow", Overflow(self))
        self.__system = system

    def getActuator(self, name):
        return self.__system.getActuator(name)
        
    def getSensor(self, name):
        return self.__system.getSensor(name)
    
    def getConfiguration(self, name):
        return self.__system.getConfiguration(name)

    @asyncio.coroutine
    def do_backwash(self):
        log.info("Do Backwash")
        pump = self.getActuator("pump-main")
        valve = self.getActuator("valve-1")
        yield from pump.stop()
        yield from asyncio.sleep(1)
        yield from valve.close()
        yield from asyncio.sleep(1)
        yield from pump.start()
        try:
            yield from asyncio.wait_for(self.getSensor("pressure-main").below(2.0), 20)
        except asyncio.TimeoutError:
            log.warning("Washing takes too long, interrupting...")
        yield from pump.stop()
        yield from asyncio.sleep(1)
        log.info("Backwash done")
        yield from self.do_economy()

    @asyncio.coroutine
    def do_overflow(self):
        log.info("Do Overflow")
        pump = self.getActuator("pump-main")
        valve = self.getActuator("valve-1")
        yield from valve.open()
        yield from pump.start()
        yield from self.overflow()
    
    @asyncio.coroutine
    def overflow(self):
        log.info("Overflow")
        settings = self.getConfiguration("settings")
        if not settings.getRunning():
            yield from self.do_standby()
        if settings.getFiltration() is "economy":
            yield from self.do_economy()
        yield from asyncio.sleep(1)
        yield from self.overflow()

    @asyncio.coroutine
    def do_economy(self):
        log.info("Do Economy")
        pump = self.getActuator("pump-main")
        valve = self.getActuator("valve-1")
        yield from valve.close()
        yield from pump.start()
        yield from self.economy()

    @asyncio.coroutine
    def economy(self):
        log.info("Economy")
        settings = self.getConfiguration("settings")
        if not settings.getRunning():
            yield from self.do_standby()
        if settings.getFiltration() is "overflow":
            yield from self.do_overflow()
        if (yield from self.getSensor("pressure-main").above(3.0)):
            yield from self.do_backwash()
        yield from asyncio.sleep(1)
        yield from self.economy()

    @asyncio.coroutine
    def do_standby(self):
        log.info("Do Standby")
        pump = self.getActuator("pump-main")
        valve = self.getActuator("valve-1")
        yield from pump.stop()
        yield from self.standby()

    @asyncio.coroutine
    def standby(self):
        log.info("Standby")
        settings = self.getConfiguration("settings")
        if settings.getRunning():
            if settings.getFiltration() is "overflow":
                yield from self.do_overflow()
            else:
                yield from self.do_economy()

    @asyncio.coroutine
    def main(self, loop):
        yield from self.do_standby()
        return
    
        settings = self.getConfiguration("settings")
        while True:
            if settings.getRunning():
                if settings.getFiltration() is "overflow":
                    yield from self.overflow()
                else:
                    yield from self.economy()
            else:
                yield from self.standby()
        
            continue
            try:
                if (yield from self.getSensor("pressure-main").above(3.0)):
                    yield from self.backwash()
                else:
                    yield from asyncio.sleep(1)
            except Exception as exception:
                log.error(exception)
                yield from self.getActuator("pump-main").stop()
                yield from asyncio.sleep(1)

