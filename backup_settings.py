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

from datetime import datetime

from controller.dispatcher import Dispatcher
from controller.mqtt import Mqtt


class BackupDispatcher(Dispatcher):
    ignore = [
        "/status/filtration/duration",
    ]

    def __init__(self, fd):
        self.__fd = fd

    def dispatch(self, topic, payload):
        if topic in self.ignore:
            return
        data = payload.decode("utf-8")
        self.__fd.write('mosquitto_pub -t %s -m "%s" -r\n' % (topic, data))


def main():
    print("Starting backup...")
    with open("backup.txt", "w") as fd:
        dispatcher = BackupDispatcher(fd)
        dispatcher.register(None, None, None, None, None, None, None, None)

        fd.write("# Backup from %s\n" % datetime.now())

        mqtt = Mqtt.start(dispatcher).proxy()
        mqtt.do_start()

        # Don't stop the client too quickly or not all messages will be published.
        import time

        time.sleep(1)

        mqtt.do_stop()
        mqtt.stop()
    print("Done")


if __name__ == "__main__":
    main()
