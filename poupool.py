import os
import time
import pykka
import logging
import logging.config
import argparse

from controller.filtration import Filtration
from controller.disinfection import Disinfection
from controller.tank import Tank
from controller.swim import Swim
from controller.dispatcher import Dispatcher
from controller.encoder import Encoder
from controller.mqtt import Mqtt
from controller.temperature import Temperature
from controller.device import DeviceRegistry, SwitchDevice, PumpDevice, TempSensorDevice, TankSensorDevice


def setup_gpio(registry):
    try:
        import RPi.GPIO as GPIO
    except RuntimeError:
        from unittest.mock import MagicMock
        GPIO = MagicMock()
    GPIO.setmode(GPIO.BOARD)

    registry.add_pump(PumpDevice("variable", GPIO, [37, 40, 38, 36]))
    registry.add_pump(SwitchDevice("boost", GPIO, 7))
    registry.add_pump(SwitchDevice("swim", GPIO, 11))

    registry.add_pump(SwitchDevice("ph", GPIO, 22))
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
        from unittest.mock import MagicMock
        adc = MagicMock()
        adc.read_adc = MagicMock(return_value=2048)
    registry.add_sensor(TankSensorDevice("tank", adc, 0, 2 / 3, 12, 4002))
    # 28-031634d04aff
    # 28-0416350909ff
    registry.add_sensor(TempSensorDevice("temperature_pool", "28-031634d04aff"))
    registry.add_sensor(TempSensorDevice("temperature_air", "28-0416350909ff"))


def toggle_test(device):
    print("Toggling %s " % device.name, end="")
    result = input("[y/N]: ")
    if result == "y":
        time.sleep(2)
        device.on()
        time.sleep(2)
        device.off()


def read_test(device):
    print("Read %s " % device.name, end="")
    result = input("[y/N]: ")
    if result == "y":
        for _ in range(5):
            print(device.value)
            time.sleep(1)


def test(args):
    devices = DeviceRegistry()
    setup_gpio(devices)

    pump = devices.get_pump("variable")
    print("Toggling %s " % pump.name, end="")
    result = input("[y/N]: ")
    if result == "y":
        for speed in reversed(range(4)):
            print("%s: speed %d" % (pump.name, speed))
            pump.speed(speed)
            time.sleep(2)
    toggle_test(devices.get_pump("boost"))
    toggle_test(devices.get_pump("swim"))
    toggle_test(devices.get_pump("ph"))
    toggle_test(devices.get_pump("cl"))

    toggle_test(devices.get_valve("gravity"))
    toggle_test(devices.get_valve("backwash"))
    toggle_test(devices.get_valve("tank"))
    toggle_test(devices.get_valve("drain"))
    toggle_test(devices.get_valve("main"))

    read_test(devices.get_sensor("temperature_pool"))
    read_test(devices.get_sensor("temperature_air"))
    read_test(devices.get_sensor("tank"))


def main(args):
    devices = DeviceRegistry()
    setup_gpio(devices)

    dispatcher = Dispatcher()

    mqtt = Mqtt.start(dispatcher).proxy()
    encoder = Encoder(mqtt)

    filtration = Filtration.start(encoder, devices).proxy()
    swim = Swim.start(encoder, devices).proxy()
    tank = Tank.start(encoder, devices, args.no_tank).proxy()
    disinfection = Disinfection.start(encoder, devices, args.no_disinfection).proxy()

    dispatcher.register(filtration, swim)

    sensors = [devices.get_sensor("temperature_pool"), devices.get_sensor("temperature_air")]
    temperature = Temperature.start(encoder, sensors).proxy()

    mqtt.do_start()
    temperature.do_read()

    # Wait forever
    while True:
        time.sleep(1000)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-config", action="store",
                        default="logging.conf", help="log configuration file")
    parser.add_argument("--no-tank", action="store_true", help="disable tank support")
    parser.add_argument("--no-disinfection", action="store_true",
                        help="disable disinfection support")
    parser.add_argument("--test-mode", action="store_true", help="test mode")
    args = parser.parse_args()

    # Setup logging
    if os.path.isfile(args.log_config):
        logging.config.fileConfig(args.log_config, disable_existing_loggers=False)
    else:
        logging.error("Log configuration file (%s) cannot be used" % args.log_config)

    try:
        if args.test_mode:
            test(args)
        else:
            main(args)
    except KeyboardInterrupt:
        pykka.ActorRegistry.stop_all()
