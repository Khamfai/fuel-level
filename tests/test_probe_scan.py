"""probe_scan: field tool to find which console tanks answer and print raw readings."""

import io
import unittest
from contextlib import redirect_stdout

from pokcenser.probe import PokTimeout
from pokcenser.protocol import ProbeReading
from probe_scan import find_tanks, print_readings


class FakeProbe:
    """read(tank) answers from a dict; missing tanks time out."""

    def __init__(self, readings):
        self._readings = readings
        self.polled = []

    def read(self, tank):
        self.polled.append(tank)
        if tank not in self._readings:
            raise PokTimeout("no reply within 2.0s (2 bytes received: e2 42)")
        return self._readings[tank]


class FindTanksTest(unittest.TestCase):
    def test_polls_tanks_1_to_8_and_lists_the_ones_that_answer(self):
        probe = FakeProbe({3: ProbeReading(1564.0, 87.1, 26.9)})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(find_tanks(probe), [3])
        self.assertEqual(probe.polled, list(range(1, 9)))


class PrintReadingsTest(unittest.TestCase):
    def test_prints_one_line_per_tank_and_reports_failures(self):
        probe = FakeProbe({3: ProbeReading(1564.0, 87.1, 26.9)})
        out = io.StringIO()
        with redirect_stdout(out):
            failures = print_readings(probe, [3, 4])
        lines = out.getvalue().splitlines()
        self.assertIn("1564.0", lines[0])
        self.assertIn("FAILED", lines[1])
        self.assertEqual(failures, 1)


if __name__ == "__main__":
    unittest.main()
