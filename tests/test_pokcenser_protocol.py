"""ASCII poll/reply protocol captured from a Pokcenser PWD-CM1 console talking to a PWL-M200 probe.

Frames captured on the wire at 4800 8N1 (tank 3 on the console):
    console -> probe   E2 42                       (0xE0 + tank - 1, then "B")
    probe -> console   02 "1564.0:87.1:27.0" 03 50 (STX fuel:water:temp ETX crc8)
"""

import unittest

from pokcenser.protocol import (
    POKCENSER_FUNCTION,
    ProbeReading,
    PokcenserError,
    build_poll,
    crc8,
    extract_reply,
    parse_reply,
)
from tls.protocol import ProtocolError

REPLY_A = b"\x02" + b"1564.0:87.1:27.0" + b"\x03" + bytes([0x50])
REPLY_B = b"\x02" + b"1564.0:87.1:27.1" + b"\x03" + bytes([0x94])
REPLY_C = b"\x02" + b"1564.0:86.9:27.0" + b"\x03" + bytes([0x05])


class BuildPollTest(unittest.TestCase):
    def test_tank_3_is_e2_b(self):
        self.assertEqual(build_poll(3), b"\xe2B")

    def test_tank_1_is_e0_b(self):
        self.assertEqual(build_poll(1), b"\xe0B")

    def test_rejects_tank_outside_1_to_32(self):
        for bad in (0, 33):
            with self.assertRaises(ValueError):
                build_poll(bad)


class Crc8Test(unittest.TestCase):
    def test_matches_all_three_captured_replies(self):
        for reply in (REPLY_A, REPLY_B, REPLY_C):
            self.assertEqual(crc8(reply[:-1]), reply[-1], reply)


class ParseReplyTest(unittest.TestCase):
    def test_decodes_fuel_water_temperature(self):
        reading = parse_reply(REPLY_A)
        self.assertEqual(reading, ProbeReading(fuel_mm=1564.0, water_mm=87.1, temperature_c=27.0))

    def test_rejects_bad_crc(self):
        with self.assertRaisesRegex(PokcenserError, "crc"):
            parse_reply(REPLY_A[:-1] + b"\x00")

    def test_rejects_missing_framing(self):
        with self.assertRaises(PokcenserError):
            parse_reply(b"1564.0:87.1:27.0")

    def test_rejects_wrong_field_count(self):
        body = b"\x02" + b"1564.0:87.1" + b"\x03"
        with self.assertRaisesRegex(PokcenserError, "3 fields"):
            parse_reply(body + bytes([crc8(body)]))

    def test_rejects_non_numeric_field(self):
        body = b"\x02" + b"abc:87.1:27.0" + b"\x03"
        with self.assertRaises(PokcenserError):
            parse_reply(body + bytes([crc8(body)]))

    def test_error_is_a_protocol_error_for_the_poll_loop(self):
        self.assertTrue(issubclass(PokcenserError, ProtocolError))

    def test_function_label(self):
        self.assertEqual(POKCENSER_FUNCTION, "pokcenser")


class ExtractReplyTest(unittest.TestCase):
    def test_skips_echo_and_other_polls_before_the_frame(self):
        # Converter echo of our poll, a console poll for another tank, then the reply.
        buf = b"\xe2B" + b"\xe0B" + REPLY_A
        self.assertEqual(extract_reply(buf), REPLY_A)

    def test_returns_none_while_frame_incomplete(self):
        self.assertIsNone(extract_reply(b"\xe2B" + REPLY_A[:-1]))
        self.assertIsNone(extract_reply(b"\xe2B"))

    def test_ignores_trailing_bytes(self):
        self.assertEqual(extract_reply(REPLY_A + b"\xe0B"), REPLY_A)


if __name__ == "__main__":
    unittest.main()
