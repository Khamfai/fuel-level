"""PwlProbe: one Modbus address per tank, decoded into the same dataclasses the TLS path produces."""

import unittest

from modbus.probe import PROBE_FUNCTION, PwlProbe
from modbus.rtu import ModbusTimeout
from tls.protocol import InventoryReport, ProtocolError, TankInventory

# Register bytes from the protocol document's worked example (fuel 2276.6 mm, water 1320.9 mm, 18.19 C).
DOC_DATA = bytes.fromhex("0E 45 B2 49 A5 44 95 1C 91 41 00 80 91 41 00 80") + bytes(16)


class FakeBus:
    """read_input_registers answers per address; an Exception value is raised instead."""

    def __init__(self, replies):
        self._replies = replies
        self.calls = []

    def read_input_registers(self, address, start, count):
        self.calls.append((address, start, count))
        reply = self._replies[address]
        if isinstance(reply, Exception):
            raise reply
        return reply


def probe_with(replies, addresses):
    p = PwlProbe("fake", addresses=addresses)
    p._bus = FakeBus(replies)
    return p


class ReadTest(unittest.TestCase):
    def test_decodes_documented_registers(self):
        p = probe_with({2: DOC_DATA}, addresses=[2])
        reading = p.read(2)
        self.assertAlmostEqual(reading.fuel_mm, 2276.6, places=1)
        self.assertAlmostEqual(reading.water_mm, 1320.9, places=1)
        self.assertAlmostEqual(reading.temperature_c, 18.19, places=2)
        self.assertAlmostEqual(reading.point_temperatures_c[0], 18.19, places=2)
        self.assertEqual(reading.point_temperatures_c[1:], (0.0, 0.0, 0.0, 0.0))

    def test_reads_sixteen_registers_from_zero(self):
        p = probe_with({2: DOC_DATA}, addresses=[2])
        p.read(2)
        self.assertEqual(p._bus.calls, [(2, 0, 16)])

    def test_requires_context_manager(self):
        with self.assertRaises(RuntimeError):
            PwlProbe("fake", addresses=[1]).read(1)


class InventoryTest(unittest.TestCase):
    def test_builds_inventory_report_with_zero_volumes(self):
        p = probe_with({1: DOC_DATA}, addresses=[1])
        report = p.inventory()
        self.assertIsInstance(report, InventoryReport)
        self.assertEqual(report.function, PROBE_FUNCTION)
        self.assertIsNone(report.timestamp)
        tank = report.tanks[0]
        self.assertIsInstance(tank, TankInventory)
        self.assertEqual(tank.tank, 1)
        self.assertEqual((tank.fuel_volume, tank.tc_volume, tank.ullage, tank.water_volume), (0.0, 0.0, 0.0, 0.0))
        self.assertAlmostEqual(tank.fuel_height, 2276.6, places=1)
        self.assertAlmostEqual(tank.water_height, 1320.9, places=1)
        self.assertAlmostEqual(tank.temperature, 18.19, places=2)

    def test_numbers_tanks_by_position_in_address_list(self):
        p = probe_with({5: DOC_DATA, 7: DOC_DATA}, addresses=[5, 7])
        report = p.inventory()
        self.assertEqual([t.tank for t in report.tanks], [1, 2])
        self.assertEqual([c[0] for c in p._bus.calls], [5, 7])

    def test_skips_an_unreachable_probe_and_keeps_the_rest(self):
        p = probe_with({1: ModbusTimeout("silent"), 2: DOC_DATA}, addresses=[1, 2])
        with self.assertLogs("modbus.probe", level="ERROR") as logs:
            report = p.inventory()
        self.assertEqual([t.tank for t in report.tanks], [2])
        self.assertIn("address 1", logs.output[0])

    def test_raises_protocol_error_when_every_probe_fails(self):
        p = probe_with({1: ModbusTimeout("silent")}, addresses=[1])
        with self.assertLogs("modbus.probe", level="ERROR"), self.assertRaises(ProtocolError):
            p.inventory()

    def test_ignores_tls_style_tank_argument(self):
        # collect() passes the TLS "00" tank selector; the probe list already says which tanks to read.
        p = probe_with({1: DOC_DATA}, addresses=[1])
        self.assertEqual(len(p.inventory("00").tanks), 1)


if __name__ == "__main__":
    unittest.main()
