import asyncio
import logging
from controller.fsm import Fsm, FsmState, FsmTask

log = logging.getLogger("poupool.%s" % __name__)

class Stopping(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)

    async def run(self):
        print("Stopping filtration")
        await self.get_fsm().get_heating_fsm().add_event("stop")

    def transition(self, event):
        if event == "heating_stopped":
            return "stop"
        return None

class Stop(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    async def run(self):
        print("Filtration stopped")
        await asyncio.sleep(1)

    def transition(self, event):
        if event == "economy":
            return "economy"
        if event == "overflow":
            return "overflow"
        return None

class Economy(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    async def run(self):
        print("Economy")
        while True:
            if (await self.get_fsm().getSensor("pressure-main").above(3.0)):
                print("Backwash")
            await asyncio.sleep(1)

    def transition(self, event):
        if event == "stop":
            return "stopping"
        if event == "overflow":
            return "overflow"
        return None

class Overflow(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    async def run(self):
        print("Overflow")
        await asyncio.sleep(1)

    def transition(self, event):
        if event == "stop":
            return "stopping"
        if event == "economy":
            return "economy"
        return None


class Filtration(Fsm):

    def __init__(self, system):
        super().__init__()
        self.add_state("stop", Stop(self))
        self.add_state("stopping", Stopping(self))
        self.add_state("economy", Economy(self))
        self.add_state("overflow", Overflow(self))
        self.__system = system

    def get_heating_fsm(self):
        return self.__system.getFsm("heating")

    def getActuator(self, name):
        return self.__system.getActuator(name)
        
    def getSensor(self, name):
        return self.__system.getSensor(name)
    
    def getConfiguration(self, name):
        return self.__system.getConfiguration(name)

    async def do_backwash(self):
        log.info("Do Backwash")
        pump = self.getActuator("pump-main")
        valve = self.getActuator("valve-1")
        await pump.stop()
        await asyncio.sleep(1)
        await valve.close()
        await asyncio.sleep(1)
        await pump.start()
        try:
            await asyncio.wait_for(self.getSensor("pressure-main").below(2.0), 20)
        except asyncio.TimeoutError:
            log.warning("Washing takes too long, interrupting...")
        await pump.stop()
        await asyncio.sleep(1)
        log.info("Backwash done")
        await self.do_economy()

    async def do_overflow(self):
        log.info("Do Overflow")
        pump = self.getActuator("pump-main")
        valve = self.getActuator("valve-1")
        await valve.open()
        await pump.start()
        await self.overflow()
    
    async def overflow(self):
        log.info("Overflow")
        settings = self.getConfiguration("settings")
        if not settings.getRunning():
            await self.do_standby()
        if settings.getFiltration() is "economy":
            await self.do_economy()
        await asyncio.sleep(1)
        await self.overflow()

    async def do_economy(self):
        log.info("Do Economy")
        pump = self.getActuator("pump-main")
        valve = self.getActuator("valve-1")
        await valve.close()
        await pump.start()
        await self.economy()

    async def economy(self):
        log.info("Economy")
        settings = self.getConfiguration("settings")
        if not settings.getRunning():
            await self.do_standby()
        if settings.getFiltration() is "overflow":
            await self.do_overflow()
        if await self.getSensor("pressure-main").above(3.0):
            await self.do_backwash()
        await asyncio.sleep(1)
        await self.economy()

    async def do_standby(self):
        log.info("Do Standby")
        pump = self.getActuator("pump-main")
        valve = self.getActuator("valve-1")
        await pump.stop()
        await self.standby()

    async def standby(self):
        log.info("Standby")
        settings = self.getConfiguration("settings")
        if settings.getRunning():
            if settings.getFiltration() is "overflow":
                await self.do_overflow()
            else:
                await self.do_economy()

    async def main(self, loop):
        #await self.do_standby()
        return
    
        settings = self.getConfiguration("settings")
        while True:
            if settings.getRunning():
                if settings.getFiltration() is "overflow":
                    await self.overflow()
                else:
                    await self.economy()
            else:
                await self.standby()
        
            continue
            try:
                if (await self.getSensor("pressure-main").above(3.0)):
                    await self.backwash()
                else:
                    await asyncio.sleep(1)
            except Exception as exception:
                log.error(exception)
                await self.getActuator("pump-main").stop()
                await asyncio.sleep(1)

