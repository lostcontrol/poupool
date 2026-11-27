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

import pytest

from controller.config import Config, as_list


class TestConfig:
    def test_single_file(self, tmp_path):
        cfg_file = tmp_path / "config.ini"
        cfg_file.write_text("[tank]\nhysteresis = 5\neco_low = 30\n")

        cfg = Config([str(cfg_file)])
        assert cfg["tank", "hysteresis"] == "5"
        assert cfg["tank", "eco_low"] == "30"

    def test_multiple_files_override(self, tmp_path):
        base = tmp_path / "config.ini"
        local = tmp_path / "config.ini.local"
        base.write_text("[tank]\neco_low = 30\neco_high = 90\n")
        local.write_text("[tank]\neco_high = 70\n")

        cfg = Config([str(base), str(local)])
        assert cfg["tank", "eco_low"] == "30"
        assert cfg["tank", "eco_high"] == "70"

    def test_missing_key_raises(self, tmp_path):
        cfg_file = tmp_path / "config.ini"
        cfg_file.write_text("[tank]\nhysteresis = 5\n")

        cfg = Config([str(cfg_file)])
        with pytest.raises(configparser.NoOptionError):
            _ = cfg["tank", "unknown"]


class TestAsList:
    def test_default_int_list(self):
        assert as_list("26, 21, 20, 16") == [26, 21, 20, 16]

    def test_custom_type_cast(self):
        assert as_list("1.5, 2.5, 3.0", float) == [1.5, 2.5, 3.0]
        assert as_list("a,b,c", str.strip) == ["a", "b", "c"]
