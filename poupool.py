from controller.filtration import Filtration
from controller.tank import Tank
from controller.dispatcher import Dispatcher
from controller.encoder import Encoder
from controller.mqtt import Mqtt
from controller.device import DeviceRegistry, SwitchDevice, PumpDevice, SensorDevice

try:
    import RPi.GPIO as GPIO
except RuntimeError:
    from unittest.mock import MagicMock
    GPIO = MagicMock()

import time
import pykka
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)-15s %(levelname)-6s %(name)-15s %(message)s"
)
logging.getLogger("pykka").setLevel(logging.WARN)
logging.getLogger("transitions").setLevel(logging.WARN)

def setup_gpio(registry):
    GPIO.setmode(GPIO.BOARD)

    registry.add_pump(PumpDevice("variable", [38, 35, 36, 37]))
    registry.add_pump(SwitchDevice("boost", 29))
    
    registry.add_valve(SwitchDevice("gravity", 15))
    registry.add_valve(SwitchDevice("backwash", 16))
    registry.add_valve(SwitchDevice("tank", 22))
    registry.add_valve(SwitchDevice("drain", 18))
    registry.add_valve(SwitchDevice("main", 13))

    registry.add_sensor(SensorDevice("tank"))

def main():
    devices = DeviceRegistry()
    setup_gpio(devices)

    dispatcher = Dispatcher()

    mqtt = Mqtt.start(dispatcher).proxy()
    encoder = Encoder(mqtt)

    filtration = Filtration.start(encoder, devices).proxy()
    dispatcher.register(filtration)
    tank = Tank.start(encoder, devices).proxy()

    mqtt.do_start()


if __name__ == '__main__':
    try:
        main()
        while True:
            time.sleep(1000)
    except KeyboardInterrupt:
        pykka.ActorRegistry.stop_all()

