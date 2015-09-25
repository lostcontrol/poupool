
class Settings:

    def __init__(self, mqtt):
        self.__running = False
        self.__filtration = "stop"
        mqtt.register("/settings/running", self.setRunning, bool)
        mqtt.register("/settings/filtration", self.setFiltration, str)

    def getRunning(self):
        return self.__running

    def setRunning(self, value):
        if not isinstance(value, bool):
            raise Exception("bool is expected")
        self.__running = value

    def getFiltration(self):
        return self.__filtration

    def setFiltration(self, value):
        if not isinstance(value, str):
            raise Exception("string is expected")
        self.__filtration = value
