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

from controller.dispatcher import Dispatcher, between, greater_equal, to_bool, to_float, to_int, to_string


class TestDispatcherHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"), [("0", True), ("5", True), ("10", True), ("-1", False), ("11", False)]
    )
    def test_between(self, value, expected):
        pred = between(0, 10)
        assert pred(value) is expected

    @pytest.mark.parametrize(("value", "expected"), [("-1", False), ("0", True), ("42", True)])
    def test_greater_equal(self, value, expected):
        pred = greater_equal(0)
        assert pred(value) is expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("true", True),
            ("True", True),
            ("1", True),
            ("y", True),
            ("yes", True),
            ("on", True),
            ("ON", True),
            ("false", False),
            ("0", False),
            ("off", False),
            ("no", False),
        ],
    )
    def test_to_bool(self, value, expected):
        assert to_bool(value) is expected

    @pytest.mark.parametrize(("value", "expected"), [("10", 10), ("10.7", 10)])
    def test_to_int(self, value, expected):
        assert to_int(value) == expected

    def test_to_float_and_string(self):
        assert to_float("7.25") == pytest.approx(7.25)
        assert to_string(123) == "123"


@pytest.fixture
def actors(mocker):
    return {
        "filtration": mocker.Mock(),
        "tank": mocker.Mock(),
        "swim": mocker.Mock(),
        "light": mocker.Mock(),
        "heater": mocker.Mock(),
        "heating": mocker.Mock(),
        "disinfection": mocker.Mock(),
        "arduino": mocker.Mock(),
    }


@pytest.fixture
def dispatcher(actors):
    d = Dispatcher()
    d.register(
        actors["filtration"],
        actors["tank"],
        actors["swim"],
        actors["light"],
        actors["heater"],
        actors["heating"],
        actors["disinfection"],
        actors["arduino"],
    )
    return d


class TestDispatcher:
    def test_topics_empty_before_register(self):
        d = Dispatcher()
        assert list(d.topics()) == []

    def test_topics_registered(self, dispatcher):
        topics = set(dispatcher.topics())
        assert "/settings/mode" in topics
        assert "/status/water/counter" in topics
        assert len(topics) == 40

    def test_unknown_topic_ignored(self, dispatcher, actors):
        dispatcher.dispatch("/unknown/topic", b"1")
        for actor in actors.values():
            assert actor.method_calls == []

    @pytest.mark.parametrize(
        ("topic", "actor_key", "mode"),
        [
            ("/settings/mode", "filtration", "halt"),
            ("/settings/mode", "filtration", "eco"),
            ("/settings/mode", "filtration", "standby"),
            ("/settings/mode", "filtration", "overflow"),
            ("/settings/mode", "filtration", "comfort"),
            ("/settings/mode", "filtration", "sweep"),
            ("/settings/mode", "filtration", "wash"),
            ("/settings/mode", "filtration", "wintering"),
            ("/settings/swim/mode", "swim", "halt"),
            ("/settings/swim/mode", "swim", "timed"),
            ("/settings/swim/mode", "swim", "continuous"),
            ("/settings/light/mode", "light", "halt"),
            ("/settings/light/mode", "light", "on"),
        ],
    )
    def test_mode_topics_valid(self, dispatcher, actors, topic, actor_key, mode):
        dispatcher.dispatch(topic, mode.encode("utf-8"))
        getattr(actors[actor_key], mode).defer.assert_called_once_with()

    @pytest.mark.parametrize(
        ("topic", "payload"),
        [
            ("/settings/mode", b"invalid"),
            ("/settings/swim/mode", b"invalid"),
            ("/settings/light/mode", b"blink"),
        ],
    )
    def test_mode_topics_invalid_ignored(self, dispatcher, actors, topic, payload):
        dispatcher.dispatch(topic, payload)
        for actor in actors.values():
            assert actor.method_calls == []

    @pytest.mark.parametrize(
        ("topic", "payload", "actor_key", "method", "expected"),
        [
            ("/settings/filtration/duration", b"36000", "filtration", "duration", 36000),
            ("/settings/filtration/period", b"3", "filtration", "period", 3),
            ("/settings/filtration/reset_hour", b"0", "filtration", "reset_hour", 0),
            ("/settings/filtration/tank_percentage", b"0.25", "filtration", "tank_percentage", 0.25),
            ("/settings/filtration/stir_duration", b"120", "filtration", "stir_duration", 120),
            ("/settings/filtration/stir_period", b"3600", "filtration", "stir_period", 3600),
            ("/settings/filtration/boost_duration", b"300", "filtration", "boost_duration", 300),
            ("/settings/filtration/backwash/period", b"30", "filtration", "backwash_period", 30),
            (
                "/settings/filtration/backwash/backwash_duration",
                b"120",
                "filtration",
                "backwash_backwash_duration",
                120,
            ),
            ("/settings/filtration/backwash/rinse_duration", b"60", "filtration", "backwash_rinse_duration", 60),
            (
                "/status/filtration/backwash/last",
                b"Mon Jun  1 12:00:00 2026",
                "filtration",
                "backwash_last",
                "Mon Jun  1 12:00:00 2026",
            ),
            ("/settings/filtration/speed/eco", b"2", "filtration", "speed_eco", 2),
            ("/settings/filtration/speed/standby", b"0", "filtration", "speed_standby", 0),
            ("/settings/filtration/speed/overflow", b"4", "filtration", "speed_overflow", 4),
            ("/settings/filtration/overflow_in_comfort", b"on", "filtration", "overflow_in_comfort", True),
            ("/settings/filtration/auto_overflow", b"off", "filtration", "auto_overflow", False),
            ("/settings/filtration/auto_standby", b"on", "filtration", "auto_standby", True),
            ("/settings/cover/position/eco", b"50", "filtration", "cover_position_eco", 50),
            ("/settings/tank/force_empty", b"1", "tank", "force_empty", True),
            ("/settings/swim/timer", b"15", "swim", "timer", 15),
            ("/settings/swim/speed", b"80", "swim", "speed", 80),
            ("/settings/heater/setpoint", b"12.5", "heater", "setpoint", 12.5),
            ("/settings/heating/enable", b"ON", "heating", "enable", True),
            ("/settings/heating/setpoint", b"27.5", "heating", "setpoint", 27.5),
            ("/settings/heating/start_hour", b"10", "heating", "start_hour", 10),
            ("/settings/heating/min_temp", b"15", "heating", "min_temp", 15),
            ("/settings/disinfection/ph/enable", b"0", "disinfection", "ph_enable", False),
            ("/settings/disinfection/ph/setpoint", b"7.2", "disinfection", "ph_setpoint", 7.2),
            ("/settings/disinfection/ph/pterm", b"1.5", "disinfection", "ph_pterm", 1.5),
            ("/settings/disinfection/orp/enable", b"1", "disinfection", "orp_enable", True),
            ("/settings/disinfection/orp/setpoint", b"650", "disinfection", "orp_setpoint", 650),
            ("/settings/disinfection/orp/pterm", b"2.5", "disinfection", "orp_pterm", 2.5),
            ("/status/disinfection/ph/canister_empty", b"1", "disinfection", "ph_canister_empty", True),
            ("/status/disinfection/cl/canister_empty", b"0", "disinfection", "cl_canister_empty", False),
        ],
    )
    def test_dispatch_value_topics(self, dispatcher, actors, topic, payload, actor_key, method, expected):
        dispatcher.dispatch(topic, payload)
        getattr(actors[actor_key], method).defer.assert_called_once_with(expected)

    @pytest.mark.parametrize(
        ("topic", "payload"),
        [
            ("/settings/filtration/duration", b"0"),
            ("/settings/filtration/period", b"11"),
            ("/settings/filtration/tank_percentage", b"0.8"),
            ("/settings/filtration/overflow_in_comfort", b"maybe"),
            ("/settings/filtration/auto_overflow", b"2"),
            ("/settings/filtration/auto_standby", b"2"),
            ("/settings/tank/force_empty", b"yes"),
            ("/settings/swim/timer", b"61"),
            ("/settings/swim/speed", b"0"),
            ("/settings/heating/setpoint", b"9"),
            ("/settings/disinfection/ph/setpoint", b"8.5"),
            ("/settings/disinfection/orp/setpoint", b"900"),
            ("/status/water/counter", b"-1"),
        ],
    )
    def test_out_of_range_or_invalid_values_ignored(self, dispatcher, actors, topic, payload):
        dispatcher.dispatch(topic, payload)
        for actor in actors.values():
            assert actor.method_calls == []

    @pytest.mark.parametrize(
        ("topic", "payload", "actor_key", "method", "expected"),
        [
            ("/status/filtration/duration", b"1800", "filtration", "restore_duration", 1800),
            ("/status/heating/total_seconds", b"7200", "heating", "total_seconds", 7200),
            ("/status/water/counter", b"1234", "arduino", "restore_water_counter", 1234),
        ],
    )
    def test_once_topics_removed_after_first_dispatch(
        self, dispatcher, actors, topic, payload, actor_key, method, expected
    ):
        assert topic in dispatcher.topics()
        dispatcher.dispatch(topic, payload)
        getattr(actors[actor_key], method).defer.assert_called_once_with(expected)
        assert topic not in dispatcher.topics()

        actors[actor_key].reset_mock()
        dispatcher.dispatch(topic, payload)
        getattr(actors[actor_key], method).defer.assert_not_called()

    def test_malformed_payloads_caught(self, dispatcher, actors):
        dispatcher.dispatch("/settings/filtration/duration", b"\xff")
        dispatcher.dispatch("/settings/filtration/duration", b"not_a_number")
        for actor in actors.values():
            assert actor.method_calls == []
