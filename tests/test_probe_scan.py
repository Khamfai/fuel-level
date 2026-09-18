"""probe_scan: field tool to find a probe's address and print raw readings."""

import io
import unittest
from contextlib import redirect_stdout

from modbus.rtu import ModbusTimeout, crc16, parse_read_response
from pokcenser.probe import PokTimeout
from pokcenser.protocol import ProbeReading as PokReading
from probe_scan import ADDRESS_REGISTER, find_address, find_pok_tanks, print_pok_readings, print_readings, scan_settings

DOC_DATA = bytes.fromhex("0E 45 B2 49 A5 44 95 1C 91 41 00 80 91 41 00 80") + bytes(16)


class FakeBus:
    def __init__(self, replies):
        self._replies = replies
        self.calls = []

    def read_input_registers(self, address, start, count):
        self.calls.append((address, start, count))
        reply = self._replies[(address, start)]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FindAddressTest(unittest.TestCase):
    def test_broadcast_reply_from_protocol_doc_parses_to_address_7(self):
        # Doc: host 00 04 00 20 00 01 31 D1 -> probe 00 04 02 00 07 C5 32
        frame = bytes.fromhex("00 04 02 00 07 C5 32")
        self.assertEqual(crc16(frame[:-2]), bytes.fromhex("C5 32"))
        self.assertEqual(parse_read_response(frame, address=0, count=1), b"\x00\x07")

    def test_asks_register_0x20_on_broadcast_address(self):
        bus = FakeBus({(0, ADDRESS_REGISTER): b"\x00\x07"})
        self.assertEqual(find_address(bus), 7)
        self.assertEqual(bus.calls, [(0, 0x20, 1)])


class FakeOpener:
    """open(baud, parity) -> context-managed bus; only `answers` settings reply."""

    def __init__(self, answers):
        self._answers = answers
        self.tried = []

    def __call__(self, baud, parity):
        self.tried.append((baud, parity))
        reply = b"\x00\x07" if (baud, parity) in self._answers else ModbusTimeout("silent")
        return FakeBus({(0, ADDRESS_REGISTER): reply})


class ScanSettingsTest(unittest.TestCase):
    def test_returns_first_settings_that_answer(self):
        opener = FakeOpener({(19200, "E")})
        with redirect_stdout(io.StringIO()):
            found = scan_settings(opener, bauds=[9600, 19200], parities=["N", "E"])
        self.assertEqual(found, (19200, "E", 7))
        self.assertEqual(opener.tried, [(9600, "N"), (9600, "E"), (19200, "N"), (19200, "E")])

    def test_returns_none_when_nothing_answers(self):
        opener = FakeOpener(set())
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(scan_settings(opener, bauds=[9600], parities=["N"]))


class PrintReadingsTest(unittest.TestCase):
    def test_prints_one_line_per_address_and_reports_failures(self):
        bus = FakeBus({(1, 0): DOC_DATA, (2, 0): ModbusTimeout("silent")})
        out = io.StringIO()
        with redirect_stdout(out):
            failures = print_readings(bus, [1, 2])
        lines = out.getvalue().splitlines()
        self.assertIn("2276.6", lines[0])
        self.assertIn("silent", lines[1])
        self.assertEqual(failures, 1)


if __name__ == "__main__":
    unittest.main()


class FakePokProbe:
    """read(tank) answers from a dict; missing tanks time out."""

    def __init__(self, readings):
        self._readings = readings
        self.polled = []

    def read(self, tank):
        self.polled.append(tank)
        if tank not in self._readings:
            raise PokTimeout("no reply within 2.0s (2 bytes received: e2 42)")
        return self._readings[tank]


class PokcenserScanTest(unittest.TestCase):
    def test_find_polls_tanks_1_to_8_and_lists_the_ones_that_answer(self):
        probe = FakePokProbe({3: PokReading(1564.0, 87.1, 26.9)})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(find_pok_tanks(probe), [3])
        self.assertEqual(probe.polled, list(range(1, 9)))

    def test_print_pok_readings_reports_values_and_failures(self):
        probe = FakePokProbe({3: PokReading(1564.0, 87.1, 26.9)})
        out = io.StringIO()
        with redirect_stdout(out):
            failures = print_pok_readings(probe, [3, 4])
        lines = out.getvalue().splitlines()
        self.assertIn("1564.0", lines[0])
        self.assertIn("FAILED", lines[1])
        self.assertEqual(failures, 1)
