import asyncio
import logging

log = logging.getLogger("poupool.%s" % __name__)

class Fsm(object):

    def __init__(self):
        self.__queue = asyncio.Queue()
        self.__state = {}
        self.__current_state = None
        
    def add_state(self, name, state):
        if not self.__current_state:
            self.__current_state = (name, state)
        self.__state[name] = state
    
    def get_state(self, name):
        return self.__state[name]
    
    async def add_event(self, event):
        await self.__queue.put(event)
    
    async def process_event(self):
        while True:
            item = await self.__queue.get()
            (current_state_name, current_state) = self.__current_state
            new_state_name = current_state.transition(item)
            log.debug("Process from %s (%s) to %s" % (current_state_name, current_state, new_state_name))
            if new_state_name:
                #if current_state_name != new_state_name:
                new_state = self.get_state(new_state_name)
                current_state.cancel()
                new_state.do_run()
                self.__current_state = (new_state_name, new_state)

class FsmTask(object):

    def __init__(self):
        self.__task = None

    def _done(self, future):
        self.__task = None

    def do_run(self):
        if self.__task:
            raise Exception("Task already running")
        self.__task = asyncio.async(self.run())
        self.__task.add_done_callback(self._done)

    async def run(self):
        raise NotImplementedError()

    def cancel(self):
        if self.__task is not None:
            return self.__task.cancel()
        return False

class FsmState(FsmTask):
    
    def __init__(self, fsm):
        super().__init__()
        self.__fsm =  fsm

    def get_fsm(self):
        return self.__fsm

    def get_state(self, name):
        return self.__fsm.get_state(name)

    async def add_event(self, event):
        await self.__fsm.add_event(event)

    def transition(self, event):
        raise NotImplementedError()

