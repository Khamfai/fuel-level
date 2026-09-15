"""Serial transport: send a command to the gauge and collect the full frame."""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

import serial
from serial.tools import list_ports

from tls import protocol
from tls.protocol import (
    DeliveryReport,
    InventoryReport,
    ProtocolError,
    StatusReport,
    build_command,
)

DEFAULT_BAUD = 9600
DEFAULT_RESPONSE_TIMEOUT_S = 10.0
COMMAND_GAP_S = 0.5  # the gauge drops commands sent right after its previous reply
RETRIES_ON_TIMEOUT = 1
log = logging.getLogger(__name__)
T = TypeVar("T")

USB_PORT_HINTS = ("usbserial", "usbmodem", "SLAB", "wchusb", "ttyUSB", "ttyACM", "COM")


class GaugeTimeout(TimeoutError):
    """The gauge did not finish its response in time."""


def find_port() -> str:
    """Pick the first USB serial adapter, or fail with the list of ports seen."""
    ports = [p.device for p in list_ports.comports()]
    for device in ports:
        if any(hint in device for hint in USB_PORT_HINTS):
            return device
    raise SystemExit(
        "No USB serial adapter found. Pass --port explicitly.\n"
        "Ports seen: " + (", ".join(ports) or "none")
    )


class TlsGauge:
    """Context-managed connection to a TLS-350 style gauge.

    with TlsGauge("/dev/cu.usbserial-1420") as gauge:
        report = gauge.inventory()
    """

    def __init__(
        self,
        port: str,
        baud: int = DEFAULT_BAUD,
        response_timeout: float = DEFAULT_RESPONSE_TIMEOUT_S,
        verify_checksum: bool = True,
    ):
        self._port = port
        self._baud = baud
        self._response_timeout = response_timeout
        self._verify = verify_checksum
        self._ser: serial.Serial | None = None
        self._last_reply_at = 0.0

    def __enter__(self) -> "TlsGauge":
        self._ser = serial.Serial(self._port, self._baud, timeout=1)
        return self

    def __exit__(self, *exc) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def query(self, function: str, tank: str = "00") -> bytes:
        """Send a command and return the raw frame from SOH through ETX.

        Retries once on timeout; the gauge occasionally ignores a command.
        """
        for attempt in range(RETRIES_ON_TIMEOUT + 1):
            try:
                return self._query_once(function, tank)
            except GaugeTimeout as exc:
                if attempt == RETRIES_ON_TIMEOUT:
                    raise
                log.warning("%s, retrying", exc)
        raise AssertionError("unreachable")

    def _query_once(self, function: str, tank: str) -> bytes:
        if self._ser is None:
            raise RuntimeError("use TlsGauge inside a 'with' block")

        gap = COMMAND_GAP_S - (time.monotonic() - self._last_reply_at)
        if gap > 0:
            time.sleep(gap)
        self._ser.reset_input_buffer()
        self._ser.write(build_command(function, tank))

        deadline = time.monotonic() + self._response_timeout
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            data = self._ser.read_until(protocol.ETX)
            if data:
                chunks.append(data)
            if data.endswith(protocol.ETX):
                self._last_reply_at = time.monotonic()
                frame = b"".join(chunks)
                log.debug("%s%s raw response (%d bytes): %r", function, tank, len(frame), frame)
                return frame

        self._last_reply_at = time.monotonic()
        got = sum(len(c) for c in chunks)
        raise GaugeTimeout(
            f"no ETX within {self._response_timeout:.0f}s for {function}{tank} ({got} bytes received)"
        )

    def _parsed(self, function: str, tank: str, parser: Callable[[bytes, bool], T]) -> T:
        frame = self.query(function, tank)
        try:
            return parser(frame, self._verify)
        except ProtocolError as exc:
            raise ProtocolError(f"{exc} | raw={frame!r}") from exc

    def inventory(self, tank: str = "00") -> InventoryReport:
        return self._parsed(protocol.FUNCTION_INVENTORY, tank, protocol.parse_inventory_report)

    def status(self, tank: str = "00") -> StatusReport:
        return self._parsed(protocol.FUNCTION_STATUS, tank, protocol.parse_status_report)

    def last_delivery(self, tank: str = "00") -> DeliveryReport:
        return self._parsed(protocol.FUNCTION_DELIVERY, tank, protocol.parse_delivery_report)
