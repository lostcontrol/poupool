import asyncio
import logging
from controller.fsm import Fsm, FsmState, FsmTask

log = logging.getLogger("poupool.%s" % __name__)

class Stop(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    async def run(self):
        print("Stop heating")
        await self.get_fsm().get_fsm_filtration().add_event("heating_stopped")

    def transition(self, event):
        if event == "start":
            return "heat"
        if event == "stop":
            return "stop"
        return None

class Heat(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    async def run(self):
        for i in range(10):
            print("Heating...")
            await asyncio.sleep(1)
        self.add_event("stop")

    def transition(self, event):
        if event == "stop":
            self.cancel()
            return "stop"
        return None

class Heating(Fsm):

    def __init__(self, system):
        super().__init__()
        self.add_state("stop", Stop(self))
        self.add_state("heat", Heat(self))
        self.__system = system

    def get_fsm_filtration(self):
        return self.__system.getFsm("filtration")

