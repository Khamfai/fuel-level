"""Pokcenser console <-> probe protocol, reverse-engineered from the wire.

The vendor's "RS485 Protocol V2.0" document describes Modbus RTU at 9600 baud, but
the probes shipped with a PWD-CM1 console speak this instead, at 4800 8N1:

    poll   0xE0 + (tank - 1), 'B'                             2 bytes
    reply  STX "<fuel_mm>:<water_mm>:<temp_c>" ETX crc8       e.g. 02 "1564.0:87.1:27.0" 03 50

crc8 is Dallas/Maxim CRC-8 (poly 0x31 reflected = 0x8C, init 0) over STX..ETX inclusive,
brute-forced from three captured replies. The probe answers in ~0.85 s.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tls.protocol import ProtocolError

POKCENSER_FUNCTION = "pokcenser"
POLL_COMMAND = b"B"
ADDRESS_BASE = 0xE0
MIN_TANK = 1
MAX_TANK = 32
STX = b"\x02"
ETX = b"\x03"
FIELD_SEPARATOR = b":"
FIELD_COUNT = 3
CRC_LEN = 1
CRC8_REFLECTED_POLY = 0x8C


class PokcenserError(ProtocolError):
    """The reply does not match the captured frame format."""


@dataclass(frozen=True)
class ProbeReading:
    fuel_mm: float
    water_mm: float
    temperature_c: float


def build_poll(tank: int) -> bytes:
    if not MIN_TANK <= tank <= MAX_TANK:
        raise ValueError(f"tank must be {MIN_TANK}..{MAX_TANK}, got {tank}")
    return bytes([ADDRESS_BASE + tank - 1]) + POLL_COMMAND


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ CRC8_REFLECTED_POLY if crc & 1 else crc >> 1
    return crc


def extract_reply(buf: bytes) -> Optional[bytes]:
    """Return the first complete STX..ETX+crc frame in buf, or None if not (yet) there."""
    start = buf.find(STX)
    if start < 0:
        return None
    end = buf.find(ETX, start)
    if end < 0 or len(buf) < end + len(ETX) + CRC_LEN:
        return None
    return buf[start: end + len(ETX) + CRC_LEN]


def parse_reply(frame: bytes) -> ProbeReading:
    if not frame.startswith(STX) or len(frame) < len(STX) + len(ETX) + CRC_LEN or frame[-2:-1] != ETX:
        raise PokcenserError(f"reply is not STX ... ETX crc: {frame!r}")
    body, received = frame[:-CRC_LEN], frame[-1]
    expected = crc8(body)
    if received != expected:
        raise PokcenserError(f"crc mismatch: got {received:#04x}, expected {expected:#04x} for {frame!r}")
    fields = body[len(STX):-len(ETX)].split(FIELD_SEPARATOR)
    if len(fields) != FIELD_COUNT:
        raise PokcenserError(f"expected {FIELD_COUNT} fields, got {len(fields)}: {frame!r}")
    try:
        fuel, water, temperature = (float(f) for f in fields)
    except ValueError as exc:
        raise PokcenserError(f"non-numeric field in {frame!r}: {exc}") from exc
    return ProbeReading(fuel, water, temperature)
