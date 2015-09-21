import asyncio
import logging

from actuator.pump import Pump
from actuator.valve import Valve
from sensor.pressure import PressureSensor
from controller.filtration import Filtration
from mqtt.mqtt import Mqtt

logging.getLogger("poupool").setLevel(logging.DEBUG)
logging.basicConfig(format="%(asctime)-15s %(levelname)-5s %(message)s")

sensor = PressureSensor()
filtration = Filtration(Pump(), Valve(), sensor)
mqtt = Mqtt(sensor)

loop = asyncio.get_event_loop()
asyncio.async(filtration.main(loop))
asyncio.async(mqtt.main())
loop.run_forever()
