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

import paho.mqtt.client as mqtt
import logging
from .actor import PoupoolActor

logger = logging.getLogger(__name__)


class Mqtt(PoupoolActor):

    def __init__(self, dispatcher):
        super().__init__()
        self.__run = True
        self.__dispatcher = dispatcher
        self.__client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.__client.on_connect = self.__on_connect
        self.__client.on_message = self.__on_message
        self.__client.on_disconnect = self.__on_disconnect

    def on_stop(self):
        self.do_stop()
        self.__client.disconnect()

    def __on_connect(self, client, userdata, flags, rc):
        logger.info("MQTT client connected to broker")
        for topic in self.__dispatcher.topics():
            self.__client.subscribe(topic)

    def __on_message(self, client, userdata, message):
        self.__dispatcher.dispatch(message.topic, message.payload)

    def __on_disconnect(self, client, userdata, rc):
        logger.warning("MQTT client disconnected: %d" % rc)
        if rc != 0 and self.__run:
            self.do_connect()

    def do_connect(self):
        try:
            self.__client.connect("localhost")
        except Exception as e:
            logger.error("Unable to connect to MQTT broker: %s" % e)
            self.do_delay(5, self.do_connect.__name__)

    def do_start(self):
        self.do_connect()
        self._proxy.do_loop()

    def do_loop(self):
        self.__client.loop(timeout=0.05)
        if self.__run:
            self.do_delay(0, self.do_loop.__name__)

    def do_stop(self):
        self.__run = False

    def publish(self, topic, payload, qos=0, retain=False):
        result, _ = self.__client.publish(topic, payload, qos, retain)
        if result != 0:
            logger.error("Unable to publish topic '%s':'%s'" % (topic, str(payload)))
            return False
        return True
