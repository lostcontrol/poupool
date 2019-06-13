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
from serial.serialutil import SerialException


@pytest.fixture
def lcdbackpack(mocker):
    return mocker.Mock()


@pytest.fixture
def lcd(lcdbackpack):
    from controller.lcd import Lcd
    return Lcd(lcdbackpack)


class TestLcd:

    def test_do_connect(self, lcd, lcdbackpack):
        lcd.do_start()
        lcdbackpack.connect.assert_called_once_with()
        lcdbackpack.set_lcd_size.assert_called_once_with(20, 4)
        lcdbackpack.clear.assert_called_once_with()
        lcdbackpack.set_brightness.assert_called_once_with(255)
        lcdbackpack.display_on.assert_called_once_with()

    def test_do_connect_failed(self, lcd, lcdbackpack):
        lcdbackpack.connect.side_effect = SerialException()
        lcd.do_start()
        lcdbackpack.set_lcd_size.assert_not_called()
        lcdbackpack.clear.assert_not_called()
        lcdbackpack.set_brightness.assert_not_called()
        lcdbackpack.display_on.assert_not_called()

    def test_do_update(self, lcd, lcdbackpack):
        lcd.do_update()
        lcdbackpack.set_cursor_home.assert_called_once_with()
        lcdbackpack.write.assert_called_once_with("""Mode              --
Water  0.0 Air   0.0
pH     0.0 ORP     0
Next event  00:00:00""".replace("\n", ""))

    def test_halt_mode(self, lcd):
        lcd.update("filtration_state", "halt")
        assert lcd.get_printable_string() == """Mode            HALT
Water  0.0 Air   0.0
pH     0.0 ORP     0
Next event  00:00:00"""

    def test_negative_temperature(self, lcd):
        lcd.update("temperature_air", "-12.3")
        assert lcd.get_printable_string() == """Mode              --
Water  0.0 Air -12.3
pH     0.0 ORP     0
Next event  00:00:00"""

    def test_state_width_limit(self, lcd):
        lcd.update("filtration_state", "this is waaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaay too long!!!")
        assert len(lcd.get_string()) == 80
