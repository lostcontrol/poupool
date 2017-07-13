from controller.filtration import Filtration
from controller.tank import Tank
from controller.dispatcher import Dispatcher
from controller.mqtt import Mqtt
from controller.device import DeviceRegistry, SwitchDevice, PumpDevice, SensorDevice

import time
import pykka
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)-15s %(levelname)-6s %(name)-15s %(message)s"
)

def setup_gpio(registry):
    registry.add_pump(PumpDevice("variable", [1, 2, 3, 4]))
    registry.add_pump(SwitchDevice("boost", 4))
    
    registry.add_valve(SwitchDevice("gravity", 4))
    registry.add_valve(SwitchDevice("backwash", 4))
    registry.add_valve(SwitchDevice("tank", 4))
    registry.add_valve(SwitchDevice("drain", 4))
    registry.add_valve(SwitchDevice("main", 4))

    registry.add_sensor(SensorDevice("tank"))

def main():
    devices = DeviceRegistry()
    setup_gpio(devices)

    filtration = Filtration.start(devices).proxy()
    tank = Tank.start(devices).proxy()

    dispatcher = Dispatcher(filtration)
    
    mqtt = Mqtt.start(dispatcher).proxy()
    mqtt.do_start()


if __name__ == '__main__':
    try:
        main()
        while True:
            time.sleep(1000)
    except KeyboardInterrupt:
        pykka.ActorRegistry.stop_all()

