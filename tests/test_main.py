import unittest
from datetime import datetime

from main import collect, parse_args, run_once
from tls.api import ApiError
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

    # Lets FakeGauge stand in for TlsGauge(...) used as a context manager.
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    """Records calls; `heartbeat_error` makes heartbeat() raise."""

    logs_url = "http://fake/api/v1/logs"

    def __init__(self, heartbeat_error=None):
        self.calls = []
        self._heartbeat_error = heartbeat_error

    def heartbeat(self):
        self.calls.append("heartbeat")
        if self._heartbeat_error:
            raise self._heartbeat_error
        return True

    def post_log(self, payload):
        self.calls.append(("post_log", payload["site_id"]))
        return 201


def make_args(*extra):
    return parse_args(["--port", "/dev/null", "--site-id", "s1", *extra])


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


class RunOnceTest(unittest.TestCase):
    def test_sends_heartbeat_then_posts_the_log(self):
        client = FakeClient()
        with self.assertLogs("fuel-level", level="INFO"):
            run_once(make_args(), client, open_gauge=lambda *a, **k: FakeGauge())
        self.assertEqual(client.calls, ["heartbeat", ("post_log", "s1")])

    def test_heartbeat_still_goes_out_when_the_gauge_fails(self):
        client = FakeClient()
        broken = FakeGauge(inventory=GaugeTimeout("no ETX"), status=ProtocolError("bad"))
        with self.assertLogs("fuel-level", level="ERROR"), self.assertRaises(ProtocolError):
            run_once(make_args(), client, open_gauge=lambda *a, **k: broken)
        self.assertEqual(client.calls, ["heartbeat"])

    def test_a_failed_heartbeat_is_a_warning_and_does_not_block_the_post(self):
        client = FakeClient(heartbeat_error=ApiError("HTTP 404: device not found", status=404))
        with self.assertLogs("fuel-level", level="WARNING") as logs:
            run_once(make_args(), client, open_gauge=lambda *a, **k: FakeGauge())
        self.assertEqual(client.calls, ["heartbeat", ("post_log", "s1")])
        self.assertIn("heartbeat failed", logs.output[0])

    def test_no_heartbeat_flag_skips_it(self):
        client = FakeClient()
        with self.assertLogs("fuel-level", level="INFO"):
            run_once(make_args("--no-heartbeat"), client, open_gauge=lambda *a, **k: FakeGauge())
        self.assertEqual(client.calls, [("post_log", "s1")])

    def test_dry_run_prints_instead_of_posting(self):
        # No client: nothing to record; just make sure the cycle completes without a server.
        run_once(make_args("--dry-run"), None, open_gauge=lambda *a, **k: FakeGauge())


class ParseArgsTest(unittest.TestCase):
    def test_device_registration_flags_must_come_together(self):
        with self.assertRaises(SystemExit):
            parse_args(["--device-name", "Only name"])
        args = parse_args(["--device-name", "Station 7", "--lat", "13.75", "--lng", "100.5"])
        self.assertEqual((args.device_name, args.lat, args.lng), ("Station 7", 13.75, 100.5))

    def test_registration_is_optional(self):
        args = parse_args([])
        self.assertIsNone(args.device_name)
        self.assertFalse(args.no_heartbeat)


if __name__ == "__main__":
    unittest.main()
