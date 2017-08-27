import datetime
from controller.mqtt import Mqtt
from controller.dispatcher import Dispatcher


class FakeDispatcher(object):

    def topics(self):
        return []


def main():
    dispatcher = Dispatcher()
    dispatcher.register(None, None, None)
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
    publish("/settings/filtration/hour_of_reset", 0)
    publish("/settings/filtration/boost_duration", 5 * 60)
    publish("/settings/filtration/tank_duration", 2 * 3600)
    publish("/settings/filtration/stir_duration", 5 * 60)
    publish("/settings/filtration/backwash_period", 30)
    publish("/settings/filtration/speed/standby", 0)
    publish("/settings/filtration/speed/overflow", 4)
    publish("/settings/swim/mode", "stop")
    publish("/settings/swim/timer", 5)
    publish("/status/filtration/backwash/last", datetime.datetime.now().strftime("%c"))
    publish("/settings/light/mode", "stop")

    print("\n**** Missing default parameters ***")
    [print(t) for t in remaining]
    print("\n\n**** Unused default parameters ***")
    [print(t) for t in missing]
    print()

    mqtt.do_stop()
    mqtt.stop()


if __name__ == '__main__':
    main()
