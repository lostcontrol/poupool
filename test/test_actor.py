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
import pykka
import time
from controller.actor import PoupoolActor


class MyPoupoolActor(PoupoolActor):

    def __init__(self):
        super().__init__()
        self.cancelled = 0
        self.run = 0
        self.single = 0
        self.long = 0

    def do_cancel(self):
        self.cancelled += 1
        super().do_cancel()

    def do_single(self):
        self.single += 1

    def do_long(self):
        time.sleep(1)
        self.long += 1
        self.do_delay(0.1, self.do_long.__name__)

    def do_run(self):
        self.run += 1
        self.do_delay(1, self.do_run.__name__)


@pytest.fixture
def poupool_actor():
    yield MyPoupoolActor.start().proxy()
    pykka.ActorRegistry.stop_all()


class TestPoupoolActor:

    def test_run_cancel(self, poupool_actor):
        poupool_actor.do_run()
        time.sleep(4.5)
        poupool_actor.do_cancel()
        time.sleep(2)
        assert poupool_actor.run.get() == 5
        assert poupool_actor.cancelled.get() == 1

    def test_do_delay_multiple(self, poupool_actor):
        for _ in range(4):
            poupool_actor.do_delay(1, "do_single")
        time.sleep(2)
        assert poupool_actor.single.get() == 1
        assert poupool_actor.cancelled.get() == 0

    def test_do_delay_cancel(self, poupool_actor):
        poupool_actor.do_delay(10, "do_single")
        time.sleep(2)
        poupool_actor.do_cancel()
        assert poupool_actor.single.get() == 0
        assert poupool_actor.cancelled.get() == 1

    def test_multithread_delay(self, poupool_actor):
        from threading import Thread

        def target(): return poupool_actor.do_delay(1, "do_single")
        for thread in [Thread(target=target) for _ in range(5)]:
            thread.start()
        time.sleep(2)
        assert poupool_actor.single.get() == 1
        assert poupool_actor.cancelled.get() == 0

    def test_long_cancel(self, poupool_actor):
        poupool_actor.do_long.defer()
        time.sleep(0.5)
        poupool_actor.do_cancel.defer()
        time.sleep(2)
        assert poupool_actor.long.get() == 1
        assert poupool_actor.cancelled.get() == 1
