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


def greater_equal(value):
    return lambda x: float(x) >= value


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

    def register(self, filtration, tank, swim, light, heater, heating, disinfection, arduino):
        self.__mapping = {
            "/settings/mode": (
                filtration,
                lambda x: x in (
                    "halt",
                    "eco",
                    "standby",
                    "overflow",
                    "comfort",
                    "sweep",
                    "wash",
                    "wintering"
                ),
                lambda x: x,
                None,
                False,
            ),
            "/settings/filtration/duration": (
                filtration,
                between(1, 172800),
                lambda _: "duration",
                to_int,
                False,
            ),
            "/settings/filtration/period": (
                filtration,
                between(1, 10),
                lambda _: "period",
                to_int,
                False,
            ),
            "/settings/filtration/reset_hour": (
                filtration,
                between(0, 23),
                lambda _: "reset_hour",
                to_int,
                False,
            ),
            "/settings/filtration/tank_percentage": (
                filtration,
                between(0, 0.5),
                lambda _: "tank_percentage",
                to_float,
                False,
            ),
            "/settings/filtration/stir_duration": (
                filtration,
                between(0, 10 * 60),
                lambda _: "stir_duration",
                to_int,
                False,
            ),
            "/settings/filtration/stir_period": (
                filtration,
                between(0, 7200),
                lambda _: "stir_period",
                to_int,
                False,
            ),
            "/settings/filtration/boost_duration": (
                filtration,
                between(0, 10 * 60),
                lambda _: "boost_duration",
                to_int,
                False,
            ),
            "/settings/filtration/backwash/period": (
                filtration,
                between(0, 90),
                lambda _: "backwash_period",
                to_int,
                False,
            ),
            "/settings/filtration/backwash/backwash_duration": (
                filtration,
                between(0, 300),
                lambda _: "backwash_backwash_duration",
                to_int,
                False,
            ),
            "/settings/filtration/backwash/rinse_duration": (
                filtration,
                between(0, 300),
                lambda _: "backwash_rinse_duration",
                to_int,
                False,
            ),
            "/status/filtration/backwash/last": (
                filtration,
                lambda _: True,
                lambda _: "backwash_last",
                to_string,
                False,
            ),
            "/status/filtration/duration": (
                filtration,
                between(0, 86400),
                lambda _: "restore_duration",
                to_int,
                True,
            ),
            "/settings/filtration/speed/eco": (
                filtration,
                between(1, 3),
                lambda _: "speed_eco",
                to_int,
                False,
            ),
            "/settings/filtration/speed/standby": (
                filtration,
                between(0, 2),
                lambda _: "speed_standby",
                to_int,
                False,
            ),
            "/settings/filtration/speed/overflow": (
                filtration,
                between(1, 4),
                lambda _: "speed_overflow",
                to_int,
                False,
            ),
            "/settings/filtration/overflow_in_comfort": (
                filtration,
                lambda x: x.lower() in ("0", "1", "off", "on"),
                lambda _: "overflow_in_comfort",
                to_bool,
                False,
            ),
            "/settings/cover/position/eco": (
                filtration,
                between(0, 100),
                lambda _: "cover_position_eco",
                to_int,
                False,
            ),
            "/settings/tank/force_empty": (
                tank,
                lambda x: x.lower() in ("0", "1", "off", "on"),
                lambda _: "force_empty",
                to_bool,
                False,
            ),
            "/settings/swim/mode": (
                swim,
                lambda x: x in ("halt", "timed", "continuous"),
                lambda x: x,
                None,
                False,
            ),
            "/settings/swim/timer": (
                swim,
                between(1, 60),
                lambda _: "timer",
                to_int,
                False,
            ),
            "/settings/swim/speed": (
                swim,
                between(1, 100),
                lambda _: "speed",
                to_int,
                False,
            ),
            "/settings/light/mode": (
                light,
                lambda x: x in ("halt", "on"),
                lambda x: x,
                None,
                False,
            ),
            "/settings/heater/setpoint": (
                heater,
                between(0, 30),
                lambda _: "setpoint",
                to_float,
                False,
            ),
            "/settings/heating/enable": (
                heating,
                lambda x: x.lower() in ("0", "1", "off", "on"),
                lambda _: "enable",
                to_bool,
                False,
            ),
            "/settings/heating/setpoint": (
                heating,
                between(10, 32),
                lambda _: "setpoint",
                to_float,
                False,
            ),
            "/settings/heating/start_hour": (
                heating,
                between(0, 23),
                lambda _: "start_hour",
                to_int,
                False,
            ),
            "/settings/heating/min_temp": (
                heating,
                between(5, 25),
                lambda _: "min_temp",
                to_int,
                False,
            ),
            "/status/heating/total_seconds": (
                heating,
                lambda _: True,
                lambda _: "total_seconds",
                to_int,
                True,
            ),
            "/settings/disinfection/ph/enable": (
                disinfection,
                lambda x: x.lower() in ("0", "1", "off", "on"),
                lambda _: "ph_enable",
                to_bool,
                False,
            ),
            "/settings/disinfection/ph/setpoint": (
                disinfection,
                between(6, 8),
                lambda _: "ph_setpoint",
                to_float,
                False,
            ),
            "/settings/disinfection/ph/pterm": (
                disinfection,
                between(0, 10),
                lambda _: "ph_pterm",
                to_float,
                False,
            ),
            "/settings/disinfection/orp/enable": (
                disinfection,
                lambda x: x.lower() in ("0", "1", "off", "on"),
                lambda _: "orp_enable",
                to_bool,
                False,
            ),
            "/settings/disinfection/orp/setpoint": (
                disinfection,
                between(500, 800),
                lambda _: "orp_setpoint",
                to_int,
                False,
            ),
            "/settings/disinfection/orp/pterm": (
                disinfection,
                between(0, 10),
                lambda _: "orp_pterm",
                to_float,
                False,
            ),
            "/status/water/counter": (
                arduino,
                greater_equal(0),
                lambda _: "restore_water_counter",
                to_int,
                True,
            ),
        }

    def topics(self):
        return self.__mapping.keys()

    def dispatch(self, topic, payload):
        entry = self.__mapping.get(topic)
        if entry:
            fsm, predicate, method, value, once = entry
            try:
                data = payload.decode("utf-8")
                if predicate(data):
                    func = getattr(fsm, method(data))
                    param = value(data) if value else None
                    if param is not None:
                        func.defer(param)
                    else:
                        func.defer()
                    # Remove the entry if it should be processed only once e.g. for
                    # configuration restore at startup.
                    if once:
                        logger.debug("Removing %s, only processed once" % topic)
                        del self.__mapping[topic]
            except Exception:
                logger.exception("Unable to process data for %s: %s" % (topic, str(payload)))
