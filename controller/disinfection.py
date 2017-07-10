#from transitions.extensions import GraphMachine as Machine
from transitions import Machine

class Disinfection(object):

    states = ["stop", "running"]

    def __init__(self, devices):
        self.__devices = devices
        # Initialize the state machine
        self.__machine = Machine(model=self, states=Disinfection.states, initial="stop")
        
        self.__machine.add_transition("run", "stop", "running")
        self.__machine.add_transition("stop", "running", "stop")
    
    def on_enter_stop(self):
        self.__devices.get_pump("ph").off()
        self.__devices.get_pump("chlorine").off()
    
    def on_enter_running(self):
        self.__devices.get_pump("ph").on()
        self.__devices.get_pump("chlorine").on()
