import datetime
from controller.mqtt import Mqtt
from controller.dispatcher import Dispatcher


class FakeDispatcher(object):

    def topics(self):
        return []


def main():
    dispatcher = Dispatcher()
    dispatcher.register(None, None, None, None, None, None)
    remaining = list(dispatcher.topics())
    missing = []

    mqtt = Mqtt.start(FakeDispatcher()).proxy()
    mqtt.do_start()

    def publish(topic, value):
        settings = {"qos": 1, "retain": True}
        if topic in remaining:
            mqtt.publish(topic, value, **settings)
            remaining.remove(topic)
        else:
            missing.append(topic)

    publish("/settings/mode", "stop")
    publish("/settings/filtration/duration", 10 * 3600)
    publish("/settings/filtration/period", 3)
    publish("/settings/filtration/reset_hour", 0)
    publish("/settings/filtration/boost_duration", 5 * 60)
    publish("/settings/filtration/tank_percentage", 0.1)
    publish("/settings/filtration/stir_duration", 3 * 60)
    publish("/settings/filtration/backwash/period", 30)
    publish("/settings/filtration/backwash/backwash_duration", 120)
    publish("/settings/filtration/backwash/rinse_duration", 60)
    publish("/settings/filtration/speed/standby", 0)
    publish("/settings/filtration/speed/overflow", 4)
    publish("/settings/swim/mode", "stop")
    publish("/settings/swim/timer", 5)
    publish("/status/filtration/backwash/last", datetime.datetime.now().strftime("%c"))
    publish("/settings/light/mode", "stop")
    publish("/settings/heater/setpoint", "3.0")
    publish("/settings/heating/setpoint", "26.0")
    publish("/settings/heating/start_hour", "1")
    publish("/settings/disinfection/ph/setpoint", "7")
    publish("/settings/disinfection/ph/pterm", "1.0")
    publish("/settings/disinfection/free_chlorine", "low")
    publish("/settings/disinfection/orp/pterm", "1.0")

    print("\n**** Missing default parameters ***")
    [print(t) for t in remaining]
    print("\n\n**** Unused default parameters ***")
    [print(t) for t in missing]
    print()

    mqtt.do_stop()
    mqtt.stop()


if __name__ == '__main__':
    main()
