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

import functools
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Timer
from types import TracebackType
from typing import Self

import pykka

# from transitions.extensions import HierarchicalGraphMachine as Machine
from transitions.extensions import HierarchicalMachine as Machine

logger = logging.getLogger(__name__)


class StopRepeatException(Exception):
    pass


def do_repeat() -> Callable[[Callable[..., None]], Callable[..., None]]:
    def wrap(func: Callable[..., None]) -> Callable[..., None]:
        @functools.wraps(func)
        def wrapped_func(self: PoupoolActor, *args: object, **kwargs: object) -> None:
            try:
                func(self, *args, **kwargs)
            except StopRepeatException:
                pass
            else:
                func_name = getattr(func, "__name__", "")
                method = func_name.replace("on_enter_", "do_repeat_")
                function = getattr(self._proxy, method)
                function.defer()

        return wrapped_func

    return wrap


class PoupoolModel(Machine):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("before_state_change", []).extend(["do_cancel", self.__update_state_time])
        super().__init__(auto_transitions=False, ignore_invalid_triggers=True, **kwargs)
        self.__state_time: datetime | None = None

    def __update_state_time(self) -> None:
        self.__state_time = datetime.now()

    def get_time_in_state(self) -> timedelta:
        if self.__state_time is None:
            return timedelta(0)
        return datetime.now() - self.__state_time


class PoupoolActor(pykka.ThreadingActor):
    def __init__(self) -> None:
        super().__init__()
        self._proxy: pykka.ActorProxy[Self] = self.actor_ref.proxy()
        self.__delay_timer: Timer | None = None
        self.state: str = ""

    def on_failure(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # The actor is going to die
        logger.fatal(exception_type, exception_value, traceback)

    def on_stop(self) -> None:
        self.do_cancel()

    def get_actor(self, name: str) -> pykka.ActorProxy[pykka.ThreadingActor]:
        fsm = pykka.ActorRegistry.get_by_class_name(name)
        if fsm:
            return fsm[0].proxy()
        logger.critical(f"Actor {name} not found!!!")
        raise RuntimeError(f"Actor {name} not found!!!")

    def __do_cancel(self) -> None:
        if self.__delay_timer:
            self.__delay_timer.cancel()
            self.__delay_timer = None

    def do_cancel(self) -> None:
        self.__do_cancel()

    def do_delay(self, delay: float, method: str, *args, **kwargs) -> None:
        assert isinstance(method, str)
        assert delay >= 0
        # Stop an already running timer
        self.__do_cancel()
        func = getattr(self._proxy, method)
        if delay > 0:
            self.__delay_timer = Timer(delay, func.defer, args=args, kwargs=kwargs)
            self.__delay_timer.start()
        else:
            func.defer(*args, **kwargs)
