import unittest
from datetime import datetime

from main import collect
from tls.protocol import InventoryReport, ProtocolError, StatusReport, TankInventory
from tls.transport import GaugeTimeout

INVENTORY = InventoryReport("i201", datetime(2026, 9, 15), (TankInventory(1, 1, 0, 1, 1, 0, 20, 0),))
STATUS = StatusReport("i205", None, ())


class FakeGauge:
    def __init__(self, inventory=INVENTORY, status=STATUS):
        self._inventory, self._status = inventory, status

    def _get(self, value):
        if isinstance(value, Exception):
            raise value
        return value

    def inventory(self, tank):
        return self._get(self._inventory)

    def status(self, tank):
        return self._get(self._status)

    def last_delivery(self, tank):
        raise AssertionError("not requested")


class CollectTest(unittest.TestCase):
    def test_returns_all_requested_reports(self):
        payload = collect(FakeGauge(), ["inventory", "status"], "00", "s1")
        self.assertIn("inventory", payload)
        self.assertIn("status", payload)

    def test_skips_a_report_that_fails_and_keeps_the_rest(self):
        gauge = FakeGauge(status=ProtocolError("truncated"))
        with self.assertLogs("fuel-level", level="ERROR") as logs:
            payload = collect(gauge, ["inventory", "status"], "00", "s1")
        self.assertIn("inventory", payload)
        self.assertNotIn("status", payload)
        self.assertIn("status", logs.output[0])

    def test_raises_when_every_report_fails(self):
        gauge = FakeGauge(inventory=GaugeTimeout("no ETX"), status=ProtocolError("bad"))
        with self.assertLogs("fuel-level", level="ERROR"), self.assertRaises(ProtocolError):
            collect(gauge, ["inventory", "status"], "00", "s1")


if __name__ == "__main__":
    unittest.main()
