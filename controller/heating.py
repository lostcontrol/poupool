import asyncio
import logging
from controller.fsm import Fsm, FsmState, FsmTask

log = logging.getLogger("poupool.%s" % __name__)

class Stop(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    @asyncio.coroutine
    def run(self):
        print("Stop heating")
        yield from asyncio.sleep(1)

    def transition(self, event):
        if event == "start":
            return self.get_state("heat")
        return self

class Heat(FsmState):

    def __init__(self, fsm):
        super().__init__(fsm)
        
    @asyncio.coroutine
    def run(self):
        for i in range(10):
            print("Heating...")
            yield from asyncio.sleep(1)
        self.add_event("stop")

    def transition(self, event):
        if event == "stop":
            self.cancel()
            return self.get_state("stop")
        return self

class Heating(Fsm):

    def __init__(self, system):
        super().__init__()
        self.add_state("stop", Stop(self))
        self.add_state("heat", Heat(self))
        self.__system = system

