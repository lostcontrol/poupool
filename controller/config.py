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

import configparser


class Config:

    def __init__(self, config_files):
        self.__config = configparser.ConfigParser()
        self.__config.read(config_files)

    def __getitem__(self, pair):
        section, key = pair
        return self.__config.get(section, key)


def as_list(value, type=int):
    return [type(m) for m in value.split(",")]


config = Config(["config.ini", "config.ini.local"])
