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
def encoder(mqtt):
    from controller.encoder import Encoder
    return Encoder(mqtt)


class TestEncoder:

    def test_publish_int(self, mqtt, encoder):
        value = 10
        encoder.foo(value)
        mqtt.publish.assert_called_once_with("/status/foo", value)

    def test_publish_with_underscore(self, mqtt, encoder):
        value = "foobar"
        encoder.foo_bar(value)
        mqtt.publish.assert_called_once_with("/status/foo/bar", value)

    def test_publish_with_kwargs(self, mqtt, encoder):
        value = "foobar"
        kwargs = (1, 2)
        encoder.foo_bar(value, kw=kwargs)
        mqtt.publish.assert_called_once_with("/status/foo/bar", value, kw=kwargs)
