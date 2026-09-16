import struct
import unittest
from datetime import datetime

from tls.protocol import (
    ChecksumError,
    ProtocolError,
    build_command,
    compute_checksum,
    parse_delivery_report,
    parse_inventory_report,
    parse_status_report,
    verify_checksum,
)

SOH, ETX = b"\x01", b"\x03"


def f(value: float) -> str:
    """Encode a float as the 8-char ASCII hex IEEE-754 field the gauge uses."""
    return struct.pack(">f", value).hex().upper()


def frame(body: str) -> bytes:
    """Wrap a body in SOH ... && CCCC ETX with a valid checksum."""
    head = SOH + body.encode("ascii") + b"&&"
    return head + compute_checksum(head).encode("ascii") + ETX


class BuildCommandTest(unittest.TestCase):
    def test_builds_soh_prefixed_command(self):
        self.assertEqual(build_command("i201", "00"), b"\x01i20100")

    def test_rejects_bad_tank_number(self):
        with self.assertRaises(ValueError):
            build_command("i201", "1")


class ChecksumTest(unittest.TestCase):
    def test_sum_including_checksum_is_zero_mod_65536(self):
        head = SOH + b"i20100&&"
        total = sum(head) + int(compute_checksum(head), 16)
        self.assertEqual(total & 0xFFFF, 0)

    def test_verify_accepts_valid_frame(self):
        self.assertTrue(verify_checksum(frame("i20100")))

    def test_verify_rejects_corrupted_frame(self):
        good = frame("i20100")
        bad = good[:3] + b"X" + good[4:]
        self.assertFalse(verify_checksum(bad))


class InventoryReportTest(unittest.TestCase):
    def test_parses_two_tanks(self):
        body = (
            "i20100" + "2609151230"
            + "01" + "00000" + "07"
            + f(1000.0) + f(0.0) + f(4000.0) + f(48.25) + f(0.0) + f(76.1) + f(0.0)
            + "02" + "00000" + "07"
            + f(2500.5) + f(0.0) + f(2499.5) + f(90.0) + f(1.5) + f(70.0) + f(12.0)
        )
        report = parse_inventory_report(frame(body))

        self.assertEqual(report.function, "i201")
        self.assertEqual(report.timestamp, datetime(2026, 9, 15, 12, 30))
        self.assertEqual(len(report.tanks), 2)
        t1, t2 = report.tanks
        self.assertEqual(t1.tank, 1)
        self.assertAlmostEqual(t1.fuel_volume, 1000.0, places=3)
        self.assertAlmostEqual(t1.ullage, 4000.0, places=3)
        self.assertAlmostEqual(t1.fuel_height, 48.25, places=3)
        self.assertAlmostEqual(t1.temperature, 76.1, places=3)
        self.assertEqual(t2.tank, 2)
        self.assertAlmostEqual(t2.water_height, 1.5, places=3)
        self.assertAlmostEqual(t2.water_volume, 12.0, places=3)

    def test_parses_real_frame_from_tls350(self):
        """Captured 2026-09-15: tanks 1-2 unconfigured (all zero), tank 3 live."""
        raw = (
            b"\x01i20100260915201001000000700000000000000000000000000000000000000000000000000000000"
            b"020000007000000000000000000000000000000000000000000000000000000000"
            b"300000074620AB850000000045A54A6644BE70004401D99A41D0CCCD45A63E8F&&D604\x03"
        )
        report = parse_inventory_report(raw)

        self.assertEqual(report.timestamp, datetime(2026, 9, 15, 20, 10))
        self.assertEqual([t.tank for t in report.tanks], [1, 2, 3])
        self.assertEqual(report.tanks[0].fuel_volume, 0.0)
        t3 = report.tanks[2]
        self.assertAlmostEqual(t3.fuel_volume, 10282.88, places=2)
        self.assertAlmostEqual(t3.ullage, 5289.30, places=2)
        self.assertAlmostEqual(t3.fuel_height, 1523.5, places=1)
        self.assertAlmostEqual(t3.temperature, 26.1, places=1)

    def test_ignores_extra_fields_beyond_the_seven_documented(self):
        body = "i20101" + "0000000000" + "01" + "00000" + "09" + f(1.0) * 9
        report = parse_inventory_report(frame(body))
        self.assertIsNone(report.timestamp)
        self.assertAlmostEqual(report.tanks[0].water_volume, 1.0)

    def test_rejects_bad_checksum(self):
        good = frame("i20100" + "0000000000" + "01" + "00000" + "07" + f(1.0) * 7)
        bad = good[:-5] + b"0000" + ETX
        with self.assertRaises(ChecksumError):
            parse_inventory_report(bad)

    def test_rejects_wrong_function_code(self):
        with self.assertRaises(ProtocolError):
            parse_inventory_report(frame("i20500" + "0000000000"))

    def test_rejects_gauge_error_response(self):
        with self.assertRaises(ProtocolError):
            parse_inventory_report(SOH + b"9999FF1B" + ETX)


class StatusReportTest(unittest.TestCase):
    def test_parses_alarms(self):
        body = "i20500" + "2609151230" + "01" + "00" + "02" + "02" + "05" + "09"
        report = parse_status_report(frame(body))

        self.assertEqual(report.tanks[0].tank, 1)
        self.assertEqual(report.tanks[0].alarms, ())
        self.assertEqual(report.tanks[1].tank, 2)
        self.assertEqual([a.code for a in report.tanks[1].alarms], [5, 9])
        self.assertEqual(report.tanks[1].alarms[0].name, "Tank Low Product Alarm")

    def test_parses_real_frame_with_placeholder_alarm_codes(self):
        """Captured from a TLS-350: nn == 00 but a dummy alarm code 00 still follows."""
        report = parse_status_report(b"\x01i205002609151628010000020000030000&&F8E5\x03")

        self.assertEqual(report.timestamp, datetime(2026, 9, 15, 16, 28))
        self.assertEqual([t.tank for t in report.tanks], [1, 2, 3])
        self.assertTrue(all(t.alarms == () for t in report.tanks))

    def test_placeholder_then_real_alarm_on_next_tank(self):
        body = "i20500" + "2609151628" + "01" + "00" + "00" + "02" + "01" + "05"
        report = parse_status_report(frame(body))
        self.assertEqual(report.tanks[0].alarms, ())
        self.assertEqual([a.code for a in report.tanks[1].alarms], [5])

    def test_parses_layout_without_timestamp(self):
        """Some TLS-350 units send TTnn records straight after the tank field."""
        report = parse_status_report(frame("i20500" + "0100" + "0200" + "0300"))
        self.assertIsNone(report.timestamp)
        self.assertEqual([t.tank for t in report.tanks], [1, 2, 3])
        self.assertTrue(all(t.alarms == () for t in report.tanks))

    def test_no_timestamp_layout_with_alarms(self):
        report = parse_status_report(frame("i20500" + "0102" + "05" + "09" + "0200"))
        self.assertEqual([a.code for a in report.tanks[0].alarms], [5, 9])
        self.assertEqual(report.tanks[1].alarms, ())

    def test_still_fails_on_garbage(self):
        with self.assertRaises(ProtocolError):
            parse_status_report(frame("i20500" + "01X"))


REAL_20C_FRAME = (
    b"\x01i20C00260915155801000-001010800-0010108000A"
    + b"0" * 80 + b"02000-001010800-0010108000A" + b"0" * 80
    + b"03000-001010800-0010108000A" + b"0" * 80 + b"&&BFA8\x03"
)


class DeliveryReportTest(unittest.TestCase):
    def test_parses_real_frame_with_placeholder_records(self):
        """Captured from a TLS-350: dd == 00 but a dummy record still follows."""
        report = parse_delivery_report(REAL_20C_FRAME)

        self.assertEqual(report.timestamp, datetime(2026, 9, 15, 15, 58))
        self.assertEqual([t.tank for t in report.tanks], [1, 2, 3])
        self.assertTrue(all(t.product_code == "0" for t in report.tanks))
        self.assertTrue(all(t.deliveries == () for t in report.tanks))

    def test_tank_with_zero_deliveries_and_no_placeholder(self):
        body = "i20C00" + "2609151230" + "01" + "R" + "00" + "02" + "D" + "00"
        report = parse_delivery_report(frame(body))
        self.assertEqual([t.tank for t in report.tanks], [1, 2])

    def test_parses_one_delivery(self):
        floats = [1244.0, 1231.0, 0.0, 73.89, 3231.0, 3194.0, 0.0, 76.14, 24.4, 48.27]
        body = (
            "i20C00" + "9707290903"
            + "01" + "R" + "01" + "9707281505" + "9707281514" + "0A" + "".join(f(v) for v in floats)
            + "02" + "D" + "00"
        )
        report = parse_delivery_report(frame(body))

        self.assertEqual(report.timestamp, datetime(1997, 7, 29, 9, 3))
        t1, t2 = report.tanks
        self.assertEqual(t1.product_code, "R")
        self.assertEqual(len(t1.deliveries), 1)
        d = t1.deliveries[0]
        self.assertEqual(d.start_time, datetime(1997, 7, 28, 15, 5))
        self.assertEqual(d.end_time, datetime(1997, 7, 28, 15, 14))
        self.assertAlmostEqual(d.start_volume, 1244.0, places=2)
        self.assertAlmostEqual(d.end_volume, 3231.0, places=2)
        self.assertAlmostEqual(d.end_height, 48.27, places=2)
        self.assertAlmostEqual(d.amount, 1987.0, places=2)
        self.assertEqual(t2.deliveries, ())


if __name__ == "__main__":
    unittest.main()
