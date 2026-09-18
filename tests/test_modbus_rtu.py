"""Modbus RTU framing, checked against the worked example in
"RS485 Protocol-PWL-M200 M300-Pokcenser-V2.0" (probe address 2, read 16 input registers)."""

import unittest
from unittest.mock import patch

from modbus import rtu
from modbus.rtu import (
    CrcError,
    ModbusClient,
    ModbusError,
    ModbusTimeout,
    build_read_input_registers,
    crc16,
    decode_float_l,
    parse_read_response,
)

DOC_QUERY = bytes.fromhex("02 04 00 00 00 10 F1 F5")
DOC_DATA = bytes.fromhex("0E 45 B2 49 A5 44 95 1C 91 41 00 80 91 41 00 80") + bytes(16)
DOC_RESPONSE = bytes.fromhex("02 04 20") + DOC_DATA + bytes.fromhex("AD CA")


class Crc16Test(unittest.TestCase):
    def test_matches_documented_query_crc(self):
        self.assertEqual(crc16(DOC_QUERY[:-2]), bytes.fromhex("F1 F5"))

    def test_matches_documented_response_crc(self):
        self.assertEqual(crc16(DOC_RESPONSE[:-2]), bytes.fromhex("AD CA"))


class BuildRequestTest(unittest.TestCase):
    def test_builds_documented_read_query(self):
        self.assertEqual(build_read_input_registers(2, 0x0000, 16), DOC_QUERY)

    def test_rejects_address_outside_modbus_range(self):
        with self.assertRaises(ValueError):
            build_read_input_registers(256, 0, 1)


class ParseResponseTest(unittest.TestCase):
    def test_returns_register_bytes_from_documented_response(self):
        self.assertEqual(parse_read_response(DOC_RESPONSE, address=2, count=16), DOC_DATA)

    def test_rejects_bad_crc(self):
        corrupted = DOC_RESPONSE[:-2] + b"\x00\x00"
        with self.assertRaises(CrcError):
            parse_read_response(corrupted, address=2, count=16)

    def test_rejects_reply_from_another_address(self):
        with self.assertRaises(ModbusError):
            parse_read_response(DOC_RESPONSE, address=1, count=16)

    def test_rejects_short_frame(self):
        with self.assertRaises(ModbusError):
            parse_read_response(DOC_RESPONSE[:10], address=2, count=16)

    def test_reports_modbus_exception_code(self):
        body = bytes.fromhex("02 84 02")
        frame = body + crc16(body)
        with self.assertRaisesRegex(ModbusError, "exception 2"):
            parse_read_response(frame, address=2, count=16)


class DecodeFloatTest(unittest.TestCase):
    def test_swaps_bytes_within_each_word(self):
        # Doc: 0E 45 B2 49 is float 45 0E 49 B2 = 2276.5 mm (their rounding)
        self.assertAlmostEqual(decode_float_l(bytes.fromhex("0E 45 B2 49")), 2276.6, places=1)

    def test_temperature_example(self):
        self.assertAlmostEqual(decode_float_l(bytes.fromhex("91 41 00 80")), 18.19, places=2)


class FakeSerial:
    """Answers each write with the next queued reply; b"" means stay silent."""

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


def client_with(replies):
    c = ModbusClient("fake", response_timeout=0.05)
    c._ser = FakeSerial(replies)
    return c


class SerialSettingsTest(unittest.TestCase):
    def test_opens_port_with_requested_baud_and_parity(self):
        with patch.object(rtu.serial, "Serial") as serial_cls:
            with ModbusClient("fake", baud=19200, parity="E"):
                pass
        kwargs = serial_cls.call_args.kwargs
        self.assertEqual(serial_cls.call_args.args[:2], ("fake", 19200))
        self.assertEqual(kwargs["parity"], "E")

    def test_rejects_unknown_parity(self):
        with self.assertRaises(ValueError):
            ModbusClient("fake", parity="X")


class ModbusClientTest(unittest.TestCase):
    def test_reads_input_registers(self):
        c = client_with([DOC_RESPONSE])
        self.assertEqual(c.read_input_registers(2, 0, 16), DOC_DATA)
        self.assertEqual(c._ser.writes, [DOC_QUERY])

    def test_strips_echo_of_its_own_request(self):
        # Half-duplex converters can loop the transmitted bytes back into the receiver.
        c = client_with([DOC_QUERY + DOC_RESPONSE])
        self.assertEqual(c.read_input_registers(2, 0, 16), DOC_DATA)

    def test_strips_echo_longer_than_the_reply(self):
        # Doc §3.2: broadcast address query is 8 bytes, its reply only 7.
        query = bytes.fromhex("00 04 00 20 00 01 31 D1")
        reply = bytes.fromhex("00 04 02 00 07 C5 32")
        c = client_with([query + reply])
        self.assertEqual(c.read_input_registers(0, 0x20, 1), b"\x00\x07")

    def test_reads_short_reply_without_echo(self):
        c = client_with([bytes.fromhex("00 04 02 00 07 C5 32")])
        self.assertEqual(c.read_input_registers(0, 0x20, 1), b"\x00\x07")

    def test_times_out_when_probe_stays_silent(self):
        c = client_with([b""])
        with self.assertRaises(ModbusTimeout):
            c.read_input_registers(2, 0, 16)

    def test_requires_context_manager(self):
        with self.assertRaises(RuntimeError):
            ModbusClient("fake").read_input_registers(2, 0, 16)


if __name__ == "__main__":
    unittest.main()
