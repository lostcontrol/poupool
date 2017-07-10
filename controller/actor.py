import pykka
import transitions
import time
import logging

logger = logging.getLogger("actor")

class PoupoolModel(transitions.Machine):

    def __init__(self, *args, **kwargs):
        super(PoupoolModel, self).__init__(
            before_state_change="do_cancel",
            auto_transitions=False,
            *args,
            **kwargs
        )


class PoupoolActor(pykka.ThreadingActor):

    def __init__(self):
        super(PoupoolActor, self).__init__()
        self._proxy = self.actor_ref.proxy()
        self.__delay_cancelled = False
        self.__delay_running = False

    def get_fsm(self, name):
        fsm = pykka.ActorRegistry.get_by_class_name(name)
        if fsm:
            return fsm[0].proxy()
        logging.critical("Fsm %s not found!!!" % name)
        return None

    def do_cancel(self):
        if self.__delay_running:
            self.__delay_cancelled = True

    def do_delay(self, delay, method, *args, **kwargs):
        assert type(method) == str
        if self.__delay_cancelled:
            self.__delay_cancelled = False
            self.__delay_running = False
        elif delay > 0:
            self.__delay_running = True
            time.sleep(0.1)
            self._proxy.do_delay(delay - 0.1, method, *args, **kwargs)
        else:
            self.__delay_running = False
            func = getattr(self._proxy, method)
            func(*args, **kwargs)

