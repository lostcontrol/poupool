import unittest
from unittest.mock import MagicMock
from unittest.mock import call
from controller.filtration import Filtration


class TestFiltration(unittest.TestCase):

    def setUp(self):
        self.actuators = MagicMock()
        self.filtration = Filtration(self.actuators)

    def test_initial(self):
        self.assertEqual(self.filtration.state, "stop")

    def test_stop(self):
        self.assertTrue(self.filtration.stop())
        self.assertEqual(self.filtration.state, "stop")
        self.actuators.get_pump.assert_has_calls([
            call("variable"),
            call().off(),
            call("boost"),
            call().off(),
        ])

    def test_stop_eco(self):
        self.assertEqual(self.filtration.state, "stop")
        self.assertTrue(self.filtration.eco())
        self.assertEqual(self.filtration.state, "eco")
        self.actuators.get_pump.assert_has_calls([
            call("variable"),
            call().speed(1),
            call("boost"),
            call().off(),
        ])

    def test_stop_overflow(self):
        self.assertEqual(self.filtration.state, "stop")
        self.assertTrue(self.filtration.overflow())
        self.assertEqual(self.filtration.state, "overflow")
        self.actuators.get_pump.assert_has_calls([
            call("variable"),
            call().speed(3),
            call("boost"),
            call().on(),
        ])
    
    def test_eco_overflow(self):
        self.assertTrue(self.filtration.to_eco())
        self.assertEqual(self.filtration.state, "eco")
        self.assertTrue(self.filtration.overflow())
        self.assertEqual(self.filtration.state, "overflow")
        self.actuators.get_pump.assert_has_calls([
            call("variable"),
            call().speed(3),
            call("boost"),
            call().on(),
        ])
