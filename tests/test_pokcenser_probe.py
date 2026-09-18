"""PokProbe: poll each configured tank over serial, decode into the shared InventoryReport."""

import unittest

from pokcenser.probe import DEFAULT_BAUD, PokProbe, PokTimeout
from pokcenser.protocol import POKCENSER_FUNCTION
from tls.protocol import InventoryReport, ProtocolError, TankInventory

REPLY_T3 = b"\x02" + b"1564.0:87.1:27.0" + b"\x03" + bytes([0x50])


class FakeSerial:
    """Each write is answered with the next queued bytes (echo included); b"" stays silent."""

    def __init__(self, replies):
        self._replies = list(replies)
        self._pending = b""
        self.writes = []

    def reset_input_buffer(self):
        self._pending = b""

    def write(self, data):
        self.writes.append(data)
        self._pending = self._replies.pop(0) if self._replies else b""

    def read(self, n):
        data, self._pending = self._pending[:n], self._pending[n:]
        return data

    def close(self):
        pass


def probe_with(replies, tanks, timeout=0.05):
    p = PokProbe("fake", addresses=tanks, response_timeout=timeout)
    p._ser = FakeSerial(replies)
    return p


class ReadTest(unittest.TestCase):
    def test_default_baud_is_4800(self):
        self.assertEqual(DEFAULT_BAUD, 4800)

    def test_polls_tank_and_decodes_reply_despite_echo_and_foreign_polls(self):
        p = probe_with([b"\xe2B" + b"\xe0B" + REPLY_T3], tanks=[3])
        reading = p.read(3)
        self.assertEqual((reading.fuel_mm, reading.water_mm, reading.temperature_c), (1564.0, 87.1, 27.0))
        self.assertEqual(p._ser.writes, [b"\xe2B"])

    def test_times_out_when_probe_stays_silent(self):
        p = probe_with([b"\xe2B"], tanks=[3])
        with self.assertRaises(PokTimeout):
            p.read(3)

    def test_timeout_is_a_protocol_error_for_collect(self):
        self.assertTrue(issubclass(PokTimeout, ProtocolError))

    def test_requires_context_manager(self):
        with self.assertRaises(RuntimeError):
            PokProbe("fake", addresses=[3]).read(3)


class InventoryTest(unittest.TestCase):
    def test_tank_number_is_the_console_tank_number(self):
        p = probe_with([REPLY_T3], tanks=[3])
        report = p.inventory()
        self.assertIsInstance(report, InventoryReport)
        self.assertEqual(report.function, POKCENSER_FUNCTION)
        self.assertIsNone(report.timestamp)
        tank = report.tanks[0]
        self.assertIsInstance(tank, TankInventory)
        self.assertEqual(tank.tank, 3)
        self.assertEqual((tank.fuel_height, tank.water_height, tank.temperature), (1564.0, 87.1, 27.0))
        self.assertEqual((tank.fuel_volume, tank.tc_volume, tank.ullage, tank.water_volume), (0.0, 0.0, 0.0, 0.0))

    def test_skips_silent_tank_and_keeps_the_rest(self):
        p = probe_with([b"", REPLY_T3], tanks=[1, 3])
        with self.assertLogs("pokcenser.probe", level="ERROR") as logs:
            report = p.inventory()
        self.assertEqual([t.tank for t in report.tanks], [3])
        self.assertIn("tank 1", logs.output[0])

    def test_raises_when_every_tank_fails(self):
        p = probe_with([b""], tanks=[1])
        with self.assertLogs("pokcenser.probe", level="ERROR"), self.assertRaises(ProtocolError):
            p.inventory()

    def test_ignores_tls_style_tank_argument(self):
        p = probe_with([REPLY_T3], tanks=[3])
        self.assertEqual(len(p.inventory("00").tanks), 1)


if __name__ == "__main__":
    unittest.main()
