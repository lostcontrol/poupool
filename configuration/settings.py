import asyncio

class Settings:

    def __init__(self, mqtt, system):
        self.__system = system
        self.__running = False
        self.__filtration = "stop"
        mqtt.register("/settings/running", self.setRunning, bool)
        mqtt.register("/settings/filtration", self.setFiltration, str)

    def getRunning(self):
        return self.__running

    async def setRunning(self, value):
        if not isinstance(value, bool):
            raise Exception("bool is expected")
        if value:
            await self.__system.getFsm("filtration").add_event("running")
        self.__running = value

    def getFiltration(self):
        return self.__filtration

    async def setFiltration(self, value):
        if not isinstance(value, str):
            raise Exception("string is expected")
        if self.__filtration != value:
            await self.__system.getFsm("filtration").add_event(str(value))
        self.__filtration = value
