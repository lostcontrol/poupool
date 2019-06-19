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


class Encoder(object):

    def __init__(self, mqtt, lcd):
        self.__mqtt = mqtt
        self.__lcd = lcd

    def __getattr__(self, value):
        topic = "/status/" + "/".join(value.split("_"))
        topic = topic.replace("//", "_")

        def wrapper(x, **kwargs):
            self.__mqtt.publish.defer(topic, x, **kwargs)
            self.__lcd.update.defer(value, x)

        return wrapper
