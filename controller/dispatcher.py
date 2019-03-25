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

logger = logging.getLogger(__name__)


def between(minimum, maximum):
    return lambda x: minimum <= float(x) <= maximum


def to_bool(x):
    return x.lower() in ("true", "1", "y", "yes", "on")


def to_int(x):
    return int(float(x))


def to_float(x):
    return float(x)


def to_string(x):
    return str(x)


class Dispatcher(object):

    def __init__(self):
        self.__mapping = {}

    def register(self, filtration, swim, light, heater, heating, disinfection):
        self.__mapping = {
            "/settings/mode": (filtration, lambda x: x in ("halt", "eco", "standby", "overflow", "comfort", "sweep", "wash", "wintering"), lambda x: x, None),
            "/settings/filtration/duration": (filtration, between(1, 172800), lambda x: "duration", to_int),
            "/settings/filtration/period": (filtration, between(1, 10), lambda x: "period", to_int),
            "/settings/filtration/reset_hour": (filtration, between(0, 23), lambda x: "reset_hour", to_int),
            "/settings/filtration/tank_percentage": (filtration, between(0, 0.5), lambda x: "tank_percentage", to_float),
            "/settings/filtration/stir_duration": (filtration, between(0, 10 * 60), lambda x: "stir_duration", to_int),
            "/settings/filtration/stir_period": (filtration, between(0, 7200), lambda x: "stir_period", to_int),
            "/settings/filtration/boost_duration": (filtration, between(0, 10 * 60), lambda x: "boost_duration", to_int),
            "/settings/filtration/backwash/period": (filtration, between(0, 90), lambda x: "backwash_period", to_int),
            "/settings/filtration/backwash/backwash_duration": (filtration, between(0, 300), lambda x: "backwash_backwash_duration", to_int),
            "/settings/filtration/backwash/rinse_duration": (filtration, between(0, 300), lambda x: "backwash_rinse_duration", to_int),
            "/status/filtration/backwash/last": (filtration, lambda x: True, lambda x: "backwash_last", to_string),
            "/settings/filtration/speed/standby": (filtration, between(0, 1), lambda x: "speed_standby", to_int),
            "/settings/filtration/speed/overflow": (filtration, between(1, 4), lambda x: "speed_overflow", to_int),
            "/settings/swim/mode": (swim, lambda x: x in ("halt", "timed", "continuous"), lambda x: x, None),
            "/settings/swim/timer": (swim, between(1, 60), lambda x: "timer", to_int),
            "/settings/swim/speed": (swim, between(1, 100), lambda x: "speed", to_int),
            "/settings/light/mode": (light, lambda x: x in ("halt", "on"), lambda x: x, None),
            "/settings/heater/setpoint": (heater, between(0, 30), lambda x: "setpoint", to_float),
            "/settings/heating/enable": (heating, lambda x: x in ("0", "1"), lambda x: "enable", to_bool),
            "/settings/heating/setpoint": (heating, between(10, 30), lambda x: "setpoint", to_float),
            "/settings/heating/start_hour": (heating, between(0, 23), lambda x: "start_hour", to_int),
            "/settings/disinfection/cl/constant": (disinfection, between(0, 10), lambda x: "cl_constant", to_float),
            "/settings/disinfection/ph/enable": (disinfection, lambda x: x in ("0", "1"), lambda x: "ph_enable", to_bool),
            "/settings/disinfection/ph/setpoint": (disinfection, between(6, 8), lambda x: "ph_setpoint", to_float),
            "/settings/disinfection/ph/pterm": (disinfection, between(0, 10), lambda x: "ph_pterm", to_float),
            "/settings/disinfection/free_chlorine": (disinfection, lambda x: x in ("low", "mid", "mid_high", "high"), lambda x: "free_chlorine", to_string),
            "/settings/disinfection/orp/enable": (disinfection, lambda x: x in ("0", "1"), lambda x: "orp_enable", to_bool),
            "/settings/disinfection/orp/pterm": (disinfection, between(0, 10), lambda x: "orp_pterm", to_float),
        }

    def topics(self):
        return self.__mapping.keys()

    def dispatch(self, topic, payload):
        entry = self.__mapping.get(topic)
        if entry:
            fsm, predicate, method, value = entry
            try:
                data = payload.decode("utf-8")
                if predicate(data):
                    func = getattr(fsm, method(data))
                    param = value(data) if value else None
                    func(param) if param is not None else func()
            except Exception:
                logger.exception("Unable to process data for %s: %s" % (topic, str(payload)))
