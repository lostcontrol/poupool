import asyncio
from actuator.pump import Pump
from actuator.valve import Valve
from sensor.pressure import PressureSensor
from controller.filtration import Filtration
from mqtt.mqtt import Mqtt

sensor = PressureSensor()
filtration = Filtration(Pump(), Valve(), sensor)
mqtt = Mqtt(sensor)

loop = asyncio.get_event_loop()
asyncio.async(filtration.main(loop))
asyncio.async(mqtt.main())
#loop.run_until_complete(task)
loop.run_forever()
