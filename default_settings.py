# Poupool - swimming pool control software
# Copyright (C) 2019 Cyril Jaquier
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

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

    publish("/settings/mode", "halt")
    publish("/settings/filtration/duration", 10 * 3600)
    publish("/settings/filtration/period", 3)
    publish("/settings/filtration/reset_hour", 0)
    publish("/settings/filtration/boost_duration", 5 * 60)
    publish("/settings/filtration/tank_percentage", 0.1)
    publish("/settings/filtration/stir_duration", 2 * 60)
    publish("/settings/filtration/stir_period", 2 * 3600)
    publish("/settings/filtration/backwash/period", 30)
    publish("/settings/filtration/backwash/backwash_duration", 120)
    publish("/settings/filtration/backwash/rinse_duration", 60)
    publish("/settings/filtration/speed/eco", 1)
    publish("/settings/filtration/speed/standby", 0)
    publish("/settings/filtration/speed/overflow", 4)
    publish("/settings/cover/position/eco", 0)
    publish("/settings/tank/force_empty", "0")
    publish("/settings/swim/mode", "halt")
    publish("/settings/swim/timer", 5)
    publish("/settings/swim/speed", 50)
    publish("/status/filtration/backwash/last", datetime.datetime.now().strftime("%c"))
    publish("/settings/light/mode", "halt")
    publish("/settings/heater/setpoint", "3.0")
    publish("/settings/heating/enable", "1")
    publish("/settings/heating/setpoint", "26.0")
    publish("/settings/heating/start_hour", "1")
    publish("/settings/heating/min_temp", "15")
    publish("/settings/disinfection/cl/constant", "0.5")
    publish("/settings/disinfection/ph/enable", "1")
    publish("/settings/disinfection/ph/setpoint", "7")
    publish("/settings/disinfection/ph/pterm", "1.0")
    publish("/settings/disinfection/orp/enable", "1")
    publish("/settings/disinfection/orp/setpoint", "600")
    publish("/settings/disinfection/orp/pterm", "1.0")

    print("\n**** Missing default parameters ***")
    [print(t) for t in remaining]
    print("\n\n**** Unused default parameters ***")
    [print(t) for t in missing]
    print()

    # Don't stop the client too quickly or not all messages will be published.
    import time
    time.sleep(1)

    mqtt.do_stop()
    mqtt.stop()


if __name__ == '__main__':
    main()
