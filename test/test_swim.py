from unittest.mock import PropertyMock

import pytest


@pytest.fixture
def encoder(mocker):
    return mocker.Mock()


@pytest.fixture
def devices(mocker):
    from controller.device import DeviceRegistry, PumpDevice

    registry = DeviceRegistry()
    pump = mocker.Mock(PumpDevice)
    type(pump).name = PropertyMock(return_value="swim")
    registry.add_pump(pump)
    return registry


@pytest.fixture
def filtration(mocker):
    from controller.filtration import Filtration

    return mocker.Mock(Filtration)


@pytest.fixture
def swim(mocker, encoder, devices, filtration):
    from controller.swim import Swim

    proxy = Swim.start(None, encoder, devices).proxy()
    yield proxy
    proxy.stop()


class TestSwim:
    def test_initial_state(self, swim):
        assert swim.is_halt().get()

    def test_continuous_state(self, mocker, swim, devices, filtration):
        swim.set_filtration_state(True, False).get()
        # Devices
        pump = devices.get_pump("swim")
        pump.speed = mocker.Mock()
        pump.off = mocker.Mock()
        # Set speed
        pump_speed = 25
        swim.speed(pump_speed).get()
        # Set continuous mode
        swim.continuous().get()
        assert swim.is_continuous().get()
        # Go back to halt state
        swim.halt().get()
        assert swim.is_halt().get()
