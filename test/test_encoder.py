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


@pytest.fixture
def mqtt(mocker):
    return mocker.Mock()


@pytest.fixture
def lcd(mocker):
    return mocker.Mock()


@pytest.fixture
def encoder(mqtt, lcd):
    from controller.encoder import Encoder
    return Encoder(mqtt, lcd)


class TestEncoder:

    def test_publish_int(self, mqtt, lcd, encoder):
        value = 10
        encoder.foo(value)
        mqtt.publish.assert_called_once_with("/status/foo", value)
        lcd.update.assert_called_once_with("foo", value)

    def test_publish_with_underscore(self, mqtt, lcd, encoder):
        value = "foobar"
        encoder.foo_bar(value)
        mqtt.publish.assert_called_once_with("/status/foo/bar", value)
        lcd.update.assert_called_once_with("foo_bar", value)

    def test_publish_with_double_underscore(self, mqtt, lcd, encoder):
        value = "foobar"
        encoder.foo_bar__cat(value)
        mqtt.publish.assert_called_once_with("/status/foo/bar_cat", value)
        lcd.update.assert_called_once_with("foo_bar__cat", value)

    def test_publish_with_kwargs(self, mqtt, lcd, encoder):
        value = "foobar"
        kwargs = (1, 2)
        encoder.foo_bar(value, kw=kwargs)
        mqtt.publish.assert_called_once_with("/status/foo/bar", value, kw=kwargs)
        # No need/support for kwargs for LCD
        lcd.update.assert_called_once_with("foo_bar", value)
