import asyncio
import logging

from actuator.pump import Pump
from actuator.valve import Valve
from sensor.pressure import PressureSensor
from configuration.settings import Settings
from controller.filtration import Filtration
from controller.heating import Heating
from controller.system import System
from mqtt.mqtt import Mqtt

logging.getLogger("poupool").setLevel(logging.DEBUG)
#logging.getLogger().setLevel(logging.DEBUG)
logging.basicConfig(format="%(asctime)-15s %(levelname)-5s %(message)s")

mqtt = Mqtt()    

system = System()
system.addFsm("filtration", Filtration(system))
system.addFsm("heating", Heating(system))

system.addActuator("pump-main", Pump())
system.addActuator("valve-1", Valve())
system.addSensor("pressure-main", PressureSensor(mqtt))
system.addConfiguration("settings", Settings(mqtt, system))

loop = asyncio.get_event_loop()
loop.set_debug(True)
asyncio.async(system.getFsm("filtration").process_event())
asyncio.async(system.getFsm("heating").process_event())
asyncio.async(mqtt.main())
loop.run_forever()
