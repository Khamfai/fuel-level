import unittest
from unittest.mock import patch

from tls import transport
from tls.transport import GaugeTimeout, TlsGauge


class FakeSerial:
    """Answers with the queued reply for each write; b"" means stay silent."""

    def __init__(self, replies):
        self._replies = list(replies)
        self._pending = b""
        self.writes = []

    def reset_input_buffer(self):
        self._pending = b""

    def write(self, data):
        self.writes.append(data)
        self._pending = self._replies.pop(0) if self._replies else b""

    def read_until(self, _terminator):
        data, self._pending = self._pending, b""
        return data

    def close(self):
        pass


def gauge_with(replies, timeout=0.05):
    g = TlsGauge("fake", response_timeout=timeout)
    g._ser = FakeSerial(replies)
    return g


class QueryRetryTest(unittest.TestCase):
    @patch.object(transport, "COMMAND_GAP_S", 0)
    def test_returns_frame_on_first_reply(self):
        g = gauge_with([b"\x01i20100&&0000\x03"])
        self.assertEqual(g.query("i201"), b"\x01i20100&&0000\x03")
        self.assertEqual(len(g._ser.writes), 1)

    @patch.object(transport, "COMMAND_GAP_S", 0)
    def test_retries_once_when_gauge_stays_silent(self):
        g = gauge_with([b"", b"\x01i20500&&0000\x03"])
        with self.assertLogs("tls.transport", level="WARNING"):
            frame = g.query("i205")
        self.assertEqual(frame, b"\x01i20500&&0000\x03")
        self.assertEqual(len(g._ser.writes), 2)

    @patch.object(transport, "COMMAND_GAP_S", 0)
    def test_gives_up_after_retry(self):
        g = gauge_with([b"", b""])
        with self.assertLogs("tls.transport", level="WARNING"), self.assertRaises(GaugeTimeout):
            g.query("i205")
        self.assertEqual(len(g._ser.writes), 2)

    def test_waits_command_gap_between_commands(self):
        g = gauge_with([b"\x01i20100&&0000\x03", b"\x01i20500&&0000\x03"])
        with patch.object(transport, "COMMAND_GAP_S", 0.2), patch.object(transport.time, "sleep") as sleep:
            g.query("i201")
            g.query("i205")
        self.assertTrue(sleep.called)
        self.assertGreater(sleep.call_args[0][0], 0)


if __name__ == "__main__":
    unittest.main()
