"""Serial transport: send a command to the gauge and collect the full frame."""

from __future__ import annotations

import time

import serial
from serial.tools import list_ports

from tls import protocol
from tls.protocol import (
    DeliveryReport,
    InventoryReport,
    StatusReport,
    build_command,
)

DEFAULT_BAUD = 9600
DEFAULT_RESPONSE_TIMEOUT_S = 10.0
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

    def __enter__(self) -> "TlsGauge":
        self._ser = serial.Serial(self._port, self._baud, timeout=1)
        return self

    def __exit__(self, *exc) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def query(self, function: str, tank: str = "00") -> bytes:
        """Send a command and return the raw frame from SOH through ETX."""
        if self._ser is None:
            raise RuntimeError("use TlsGauge inside a 'with' block")

        self._ser.reset_input_buffer()
        self._ser.write(build_command(function, tank))

        deadline = time.monotonic() + self._response_timeout
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            data = self._ser.read_until(protocol.ETX)
            if data:
                chunks.append(data)
            if data.endswith(protocol.ETX):
                return b"".join(chunks)

        got = sum(len(c) for c in chunks)
        raise GaugeTimeout(
            f"no ETX within {self._response_timeout:.0f}s for {function}{tank} ({got} bytes received)"
        )

    def inventory(self, tank: str = "00") -> InventoryReport:
        return protocol.parse_inventory_report(
            self.query(protocol.FUNCTION_INVENTORY, tank), self._verify
        )

    def status(self, tank: str = "00") -> StatusReport:
        return protocol.parse_status_report(
            self.query(protocol.FUNCTION_STATUS, tank), self._verify
        )

    def last_delivery(self, tank: str = "00") -> DeliveryReport:
        return protocol.parse_delivery_report(
            self.query(protocol.FUNCTION_DELIVERY, tank), self._verify
        )
