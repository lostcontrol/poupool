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

import pytest

from controller.mqtt import Mqtt


@pytest.fixture
def dispatcher(mocker):
    d = mocker.Mock()
    d.topics.return_value = ["/settings/mode", "/settings/light/mode"]
    return d


@pytest.fixture
def mqtt_client(mocker):
    client = mocker.Mock()
    client.publish.return_value = (0, 1)
    mocker.patch("controller.mqtt.mqtt.Client", return_value=client)
    return client


@pytest.fixture
def mqtt_actor(mocker, dispatcher, mqtt_client):
    mocker.patch.object(Mqtt, "do_delay")
    proxy = Mqtt.start(dispatcher).proxy()
    yield proxy
    proxy.stop().get()


class TestMqtt:
    def test_do_start_and_do_loop(self, mocker, mqtt_actor, mqtt_client):
        do_delay_mock = mocker.patch.object(Mqtt, "do_delay")

        mqtt_actor.do_start().get()
        # Flush the do_loop() queued by do_start() before stopping
        mqtt_actor.do_stop().get()

        mqtt_client.connect.assert_called_once_with("localhost")
        mqtt_client.loop.assert_called_once_with(timeout=0.05)
        # do_stop() ran after do_loop() or wait: _proxy.do_loop() ran asynchronously after do_start()
        # Verify an explicit do_loop() when stopped does not re-schedule
        do_delay_mock.reset_mock()
        mqtt_actor.do_loop().get()
        mqtt_client.loop.assert_called_with(timeout=0.05)
        do_delay_mock.assert_not_called()

    def test_do_loop_schedules_when_running(self, mocker, mqtt_actor, mqtt_client):
        do_delay_mock = mocker.patch.object(Mqtt, "do_delay")
        mqtt_actor.do_loop().get()
        mqtt_client.loop.assert_called_once_with(timeout=0.05)
        do_delay_mock.assert_called_once_with(0, "do_loop")

    def test_do_connect_failure_schedules_retry(self, mocker, mqtt_actor, mqtt_client):
        do_delay_mock = mocker.patch.object(Mqtt, "do_delay")
        mqtt_client.connect.side_effect = OSError("broker unreachable")

        mqtt_actor.do_connect().get()
        do_delay_mock.assert_called_once_with(5, "do_connect")

    def test_callbacks_and_disconnect(self, mqtt_actor, mqtt_client, dispatcher):
        # on_connect subscribes to all dispatcher topics
        mqtt_client.on_connect(mqtt_client, None, {}, 0)
        mqtt_client.subscribe.assert_any_call("/settings/mode")
        mqtt_client.subscribe.assert_any_call("/settings/light/mode")
        assert mqtt_client.subscribe.call_count == 2

        # on_message dispatches topic and payload
        message = type("Msg", (), {"topic": "/settings/mode", "payload": b"eco"})()
        mqtt_client.on_message(mqtt_client, None, message)
        dispatcher.dispatch.assert_called_once_with("/settings/mode", b"eco")

        # on_disconnect with rc == 0 does not reconnect
        mqtt_client.on_disconnect(mqtt_client, None, 0)
        mqtt_client.connect.assert_not_called()

        # on_disconnect with rc != 0 reconnects while running
        mqtt_client.on_disconnect(mqtt_client, None, 1)
        mqtt_client.connect.assert_called_once_with("localhost")

        # on_disconnect with rc != 0 after do_stop does not reconnect
        mqtt_client.connect.reset_mock()
        mqtt_actor.do_stop().get()
        mqtt_client.on_disconnect(mqtt_client, None, 1)
        mqtt_client.connect.assert_not_called()

    def test_publish_success_and_failure(self, mqtt_actor, mqtt_client):
        mqtt_client.publish.return_value = (0, 1)
        assert mqtt_actor.publish("/status/mode", "eco", qos=1, retain=True).get() is True
        mqtt_client.publish.assert_called_once_with("/status/mode", "eco", 1, True)

        mqtt_client.publish.return_value = (1, 2)
        assert mqtt_actor.publish("/status/mode", "halt").get() is False

    def test_on_stop_disconnects(self, dispatcher, mqtt_client, mocker):
        mocker.patch.object(Mqtt, "do_delay")
        proxy = Mqtt.start(dispatcher).proxy()
        proxy.stop().get()
        mqtt_client.disconnect.assert_called_once_with()
