"""Poll Pokcenser probes with the console's ASCII protocol and build the shared InventoryReport.

Addresses are console tank numbers (tank 3 is polled with 0xE2 'B'), so the tank
number in the payload matches what the PWD-CM1 screen shows. Volumes are zero: the
probe reports heights and temperature only; the strapping table lives in the console.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Sequence

import serial

from pokcenser.protocol import POKCENSER_FUNCTION, ProbeReading, PokcenserError, build_poll, extract_reply, parse_reply
from tls.protocol import InventoryReport, ProtocolError, TankInventory

log = logging.getLogger(__name__)

DEFAULT_BAUD = 4800
DEFAULT_RESPONSE_TIMEOUT_S = 2.0  # the probe answers in ~0.85 s
SERIAL_READ_TIMEOUT_S = 0.1
READ_CHUNK = 64
COMMAND_GAP_S = 0.2  # let the bus settle between polls


class PokTimeout(ProtocolError, TimeoutError):
    """No complete reply within the response timeout."""


class PokProbe:
    """Context-managed reader for one or more probes on the same RS-485 bus.

    with PokProbe("/dev/ttyUSB0", addresses=[3]) as probe:
        report = probe.inventory()
    """

    def __init__(
        self,
        port: str,
        baud: int = DEFAULT_BAUD,
        addresses: Sequence[int] = (1,),
        response_timeout: float = DEFAULT_RESPONSE_TIMEOUT_S,
    ):
        self._port = port
        self._baud = baud
        self._addresses = tuple(addresses)
        self._response_timeout = response_timeout
        self._ser: Optional[serial.Serial] = None
        self._last_reply_at = 0.0

    def __enter__(self) -> "PokProbe":
        self._ser = serial.Serial(
            self._port,
            self._baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_READ_TIMEOUT_S,
        )
        return self

    def __exit__(self, *exc) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def read(self, tank: int) -> ProbeReading:
        if self._ser is None:
            raise RuntimeError("use PokProbe inside a 'with' block")
        gap = COMMAND_GAP_S - (time.monotonic() - self._last_reply_at)
        if gap > 0:
            time.sleep(gap)
        self._ser.reset_input_buffer()
        self._ser.write(build_poll(tank))
        frame = self._read_reply()
        log.debug("tank %d raw reply: %s", tank, frame.hex(" "))
        return parse_reply(frame)

    def _read_reply(self) -> bytes:
        """Accumulate bytes until an STX..ETX+crc frame appears; echo and foreign polls are skipped."""
        assert self._ser is not None
        deadline = time.monotonic() + self._response_timeout
        buf = b""
        while time.monotonic() < deadline:
            buf += self._ser.read(READ_CHUNK)
            frame = extract_reply(buf)
            if frame is not None:
                self._last_reply_at = time.monotonic()
                return frame
        self._last_reply_at = time.monotonic()
        raise PokTimeout(
            f"no reply within {self._response_timeout:.1f}s ({len(buf)} bytes received: {buf.hex(' ')})"
        )

    def inventory(self, tank: str = "00") -> InventoryReport:
        """Poll every configured tank; a silent tank is skipped, all silent raises."""
        tanks: list[TankInventory] = []
        failures: list[Exception] = []
        for number in self._addresses:
            try:
                reading = self.read(number)
            except (PokcenserError, PokTimeout) as exc:
                log.error("tank %d probe failed, skipping it: %s", number, exc)
                failures.append(exc)
                continue
            tanks.append(_to_tank(number, reading))
        if not tanks:
            raise ProtocolError(f"all {len(self._addresses)} probe(s) failed; last error: {failures[-1]}")
        return InventoryReport(POKCENSER_FUNCTION, None, tuple(tanks))


def _to_tank(number: int, reading: ProbeReading) -> TankInventory:
    return TankInventory(
        tank=number,
        fuel_volume=0.0,
        tc_volume=0.0,
        ullage=0.0,
        fuel_height=reading.fuel_mm,
        water_height=reading.water_mm,
        temperature=reading.temperature_c,
        water_volume=0.0,
    )
