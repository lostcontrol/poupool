
class System(object):

    def __init__(self):
        self.__actuators = {}
        self.__sensors = {}
        self.__configuration = {}

    def addActuator(self, name, actuator):
        self.__actuators[name] = actuator

    def getActuator(self, name):
        return self.__actuators[name]

    def addSensor(self, name, sensor):
        self.__sensors[name] = sensor
    
    def getSensor(self, name):
        return self.__sensors[name]

    def addConfiguration(self, name, configuration):
        self.__configuration[name] = configuration

    def getConfiguration(self, name):
        return self.__configuration[name]
