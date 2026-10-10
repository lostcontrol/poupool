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

import logging

import paho.mqtt.client as mqtt

from .actor import PoupoolActor
from .dispatcher import Dispatcher

logger = logging.getLogger(__name__)


class Mqtt(PoupoolActor):
    def __init__(self, dispatcher: Dispatcher) -> None:
        super().__init__()
        self.__run: bool = True
        self.__dispatcher: Dispatcher = dispatcher
        self.__client: mqtt.Client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.__client.on_connect = self.__on_connect
        self.__client.on_message = self.__on_message
        self.__client.on_disconnect = self.__on_disconnect

    def on_stop(self) -> None:
        self.do_stop()
        self.__client.disconnect()

    def __on_connect(self, client: mqtt.Client, userdata: object, flags: dict[str, int], rc: int) -> None:
        logger.info("MQTT client connected to broker")
        for topic in self.__dispatcher.topics():
            self.__client.subscribe(topic)

    def __on_message(self, client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage) -> None:
        self.__dispatcher.dispatch(message.topic, message.payload)

    def __on_disconnect(self, client: mqtt.Client, userdata: object, rc: int) -> None:
        logger.warning(f"MQTT client disconnected: {rc}")
        if rc != 0 and self.__run:
            self.do_connect()

    def do_connect(self) -> None:
        try:
            self.__client.connect("localhost")
        except Exception as e:
            logger.error(f"Unable to connect to MQTT broker: {e}")
            self.do_delay(5, self.do_connect.__name__)

    def do_start(self) -> None:
        self.do_connect()
        self._proxy.do_loop()

    def do_loop(self) -> None:
        self.__client.loop(timeout=0.05)
        if self.__run:
            self.do_delay(0, self.do_loop.__name__)

    def do_stop(self) -> None:
        self.__run = False

    def publish(
        self, topic: str, payload: str | bytes | int | float | None, qos: int = 0, retain: bool = False
    ) -> bool:
        result, _ = self.__client.publish(topic, payload, qos, retain)
        if result != 0:
            logger.error(f"Unable to publish topic '{topic}':'{payload!s}'")
            return False
        return True
