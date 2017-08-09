import time
import pykka
import logging
import logging.config

from controller.filtration import Filtration
from controller.disinfection import Disinfection
from controller.tank import Tank
from controller.swim import Swim
from controller.dispatcher import Dispatcher
from controller.encoder import Encoder
from controller.mqtt import Mqtt
from controller.device import DeviceRegistry, SwitchDevice, PumpDevice, TankSensorDevice


def setup_gpio(registry):
    try:
        import RPi.GPIO as GPIO
    except RuntimeError:
        from unittest.mock import MagicMock
        GPIO = MagicMock()
    GPIO.setmode(GPIO.BOARD)

    registry.add_pump(PumpDevice("variable", GPIO, [40, 36, 37, 38]))
    registry.add_pump(SwitchDevice("boost", GPIO, 12))
    registry.add_pump(SwitchDevice("swim", GPIO, 11))

    registry.add_pump(SwitchDevice("ph", GPIO, 25))
    registry.add_pump(SwitchDevice("cl", GPIO, 32))

    registry.add_valve(SwitchDevice("gravity", GPIO, 15))
    registry.add_valve(SwitchDevice("backwash", GPIO, 29))
    registry.add_valve(SwitchDevice("tank", GPIO, 33))
    registry.add_valve(SwitchDevice("drain", GPIO, 31))
    registry.add_valve(SwitchDevice("main", GPIO, 35))

    try:
        import Adafruit_ADS1x15
        adc = Adafruit_ADS1x15.ADS1015()
    except RuntimeError:
        adc = MagicMock()
        adc.read_adc = MagicMock(return_value=2048)
    registry.add_sensor(TankSensorDevice("tank", adc, 0, 2 / 3, 12, 4002))


def main():
    devices = DeviceRegistry()
    setup_gpio(devices)

    dispatcher = Dispatcher()

    mqtt = Mqtt.start(dispatcher).proxy()
    encoder = Encoder(mqtt)

    filtration = Filtration.start(encoder, devices).proxy()
    swim = Swim.start(encoder, devices).proxy()
    tank = Tank.start(encoder, devices).proxy()
    disinfection = Disinfection.start(encoder, devices).proxy()

    dispatcher.register(filtration, swim)

    mqtt.do_start()


if __name__ == '__main__':
    # Setup logging
    logging.config.fileConfig("logging.conf", disable_existing_loggers=False)
    try:
        main()
        while True:
            time.sleep(1000)
    except KeyboardInterrupt:
        pykka.ActorRegistry.stop_all()
