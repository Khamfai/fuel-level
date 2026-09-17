"""probe_scan: field tool to find a probe's address and print raw readings."""

import io
import unittest
from contextlib import redirect_stdout

from modbus.rtu import ModbusTimeout, crc16, parse_read_response
from probe_scan import ADDRESS_REGISTER, find_address, print_readings

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
