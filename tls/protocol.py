"""Frame building and parsing for Veeder-Root TLS computer-format responses.

Frame layout (see vr350-3.pdf):
    <SOH> fff TT YYMMDDHHmm <records...> && CCCC <ETX>
fff is the function code (i201, i205, i20C), TT the requested tank,
CCCC a 16-bit checksum such that sum(SOH..&&) + CCCC == 0 mod 65536.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

SOH = b"\x01"
ETX = b"\x03"
TERMINATOR = b"&&"
ERROR_FUNCTION = "9999"
PLACEHOLDER_ALARM = "00"

FUNCTION_INVENTORY = "i201"
FUNCTION_STATUS = "i205"
FUNCTION_DELIVERY = "i20C"

FLOAT_FIELD_LEN = 8
TIMESTAMP_LEN = 10
INVENTORY_UNUSED_LEN = 5
INVENTORY_FIELD_COUNT = 7
DELIVERY_FIELD_COUNT = 10

ALARM_NAMES = {
    1: "Tank Setup Data Warning",
    2: "Tank Leak Alarm",
    3: "Tank High Water Alarm",
    4: "Tank Overfill Alarm",
    5: "Tank Low Product Alarm",
    6: "Tank Sudden Loss Alarm",
    7: "Tank High Product Alarm",
    8: "Tank Invalid Fuel Level Alarm",
    9: "Tank Probe Out Alarm",
    10: "Tank High Water Warning",
    11: "Tank Delivery Needed Warning",
    12: "Tank Maximum Product Alarm",
    13: "Tank Gross Leak Test Fail Alarm",
    14: "Tank Periodic Leak Test Fail Alarm",
    15: "Tank Annual Leak Test Fail Alarm",
    16: "Tank Periodic Test Needed Warning",
    17: "Tank Annual Test Needed Warning",
    18: "Tank Periodic Test Needed Alarm",
    19: "Tank Annual Test Needed Alarm",
    20: "Tank Leak Test Active",
    21: "Tank No CSLD Idle Time Warning",
    22: "Tank Siphon Break Active Warning",
    23: "Tank CSLD Rate Increase Warning",
    24: "Tank AccuChart Calibration Warning",
    25: "Tank HRM Reconciliation Warning",
    26: "Tank HRM Reconciliation Alarm",
    27: "Tank Cold Temperature Warning",
    28: "Tank Missing Delivery Ticket Warning",
    29: "Tank/Line Gross Leak Alarm",
}


class ProtocolError(ValueError):
    """The response does not match the documented frame format."""


class ChecksumError(ProtocolError):
    """The response checksum does not match its contents."""


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TankInventory:
    tank: int
    volume: float
    tc_volume: float
    ullage: float
    height: float
    water: float
    temperature: float
    water_volume: float


@dataclass(frozen=True)
class InventoryReport:
    function: str
    timestamp: Optional[datetime]
    tanks: tuple[TankInventory, ...]


@dataclass(frozen=True)
class Alarm:
    code: int
    name: str


@dataclass(frozen=True)
class TankStatus:
    tank: int
    alarms: tuple[Alarm, ...]


@dataclass(frozen=True)
class StatusReport:
    function: str
    timestamp: Optional[datetime]
    tanks: tuple[TankStatus, ...]


@dataclass(frozen=True)
class Delivery:
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    start_volume: float
    start_tc_volume: float
    start_water: float
    start_temp: float
    end_volume: float
    end_tc_volume: float
    end_water: float
    end_temp: float
    start_height: float
    end_height: float

    @property
    def amount(self) -> float:
        return self.end_volume - self.start_volume


@dataclass(frozen=True)
class TankDelivery:
    tank: int
    product_code: str
    deliveries: tuple[Delivery, ...]


@dataclass(frozen=True)
class DeliveryReport:
    function: str
    timestamp: Optional[datetime]
    tanks: tuple[TankDelivery, ...]


# --------------------------------------------------------------------------- #
# Command / checksum helpers
# --------------------------------------------------------------------------- #

def build_command(function: str, tank: str = "00") -> bytes:
    """Return the bytes to send for a function code, e.g. b'\\x01i20100'."""
    if len(tank) != 2 or not tank.isdigit():
        raise ValueError(f"tank must be two decimal digits, got {tank!r}")
    return SOH + function.encode("ascii") + tank.encode("ascii")


def compute_checksum(head: bytes) -> str:
    """Checksum for the bytes from SOH through '&&' inclusive, as 4 hex chars."""
    return f"{(-sum(head)) & 0xFFFF:04X}"


def verify_checksum(frame: bytes) -> bool:
    end = frame.find(TERMINATOR)
    if end < 0:
        return False
    head = frame[: end + len(TERMINATOR)]
    received = frame[end + len(TERMINATOR): end + len(TERMINATOR) + 4]
    return received.decode("ascii", errors="replace").upper() == compute_checksum(head)


# --------------------------------------------------------------------------- #
# Low-level cursor over the ASCII body
# --------------------------------------------------------------------------- #

class _Cursor:
    """Sequential reader over the response body between the tank field and '&&'."""

    def __init__(self, text: str):
        self._text = text
        self._pos = 0

    def remaining(self) -> int:
        return len(self._text) - self._pos

    def peek(self, n: int) -> str:
        return self._text[self._pos: self._pos + n]

    def take(self, n: int, what: str) -> str:
        if self.remaining() < n:
            raise ProtocolError(f"truncated response while reading {what}")
        chunk = self._text[self._pos: self._pos + n]
        self._pos += n
        return chunk

    def decimal(self, n: int, what: str) -> int:
        chunk = self.take(n, what)
        if not chunk.isdigit():
            raise ProtocolError(f"expected decimal {what}, got {chunk!r}")
        return int(chunk)

    def hexadecimal(self, n: int, what: str) -> int:
        chunk = self.take(n, what)
        try:
            return int(chunk, 16)
        except ValueError as exc:
            raise ProtocolError(f"expected hex {what}, got {chunk!r}") from exc

    def timestamp(self, what: str) -> Optional[datetime]:
        return parse_timestamp(self.take(TIMESTAMP_LEN, what))

    def floats(self, count: int, what: str) -> tuple[float, ...]:
        return tuple(
            decode_float(self.take(FLOAT_FIELD_LEN, f"{what} field {i + 1}"))
            for i in range(count)
        )


def parse_timestamp(text: str) -> Optional[datetime]:
    """YYMMDDHHmm -> datetime, or None when the gauge sends zeros/garbage."""
    if len(text) != TIMESTAMP_LEN or not text.isdigit() or text == "0" * TIMESTAMP_LEN:
        return None
    try:
        return datetime.strptime(text, "%y%m%d%H%M")
    except ValueError:
        return None


def decode_float(hex8: str) -> float:
    """8 ASCII hex chars -> IEEE-754 single-precision float."""
    try:
        return struct.unpack(">f", bytes.fromhex(hex8))[0]
    except ValueError as exc:
        raise ProtocolError(f"invalid float field {hex8!r}") from exc


def _open_frame(frame: bytes, expected: str, verify: bool) -> tuple[str, _Cursor]:
    """Validate the envelope and return (requested tank, cursor over the body)."""
    if not frame.startswith(SOH) or not frame.endswith(ETX):
        raise ProtocolError("response is not wrapped in SOH ... ETX")
    function = frame[1:5].decode("ascii", errors="replace")
    if function == ERROR_FUNCTION:
        raise ProtocolError(f"gauge rejected the command: {frame[1:-1]!r}")
    if function != expected:
        raise ProtocolError(f"expected function {expected}, got {function}")
    end = frame.find(TERMINATOR)
    if end < 0:
        raise ProtocolError("response has no '&&' terminator")
    if verify and not verify_checksum(frame):
        raise ChecksumError("response checksum mismatch")

    body = frame[5:end].decode("ascii", errors="replace")
    cursor = _Cursor(body)
    tank = cursor.take(2, "tank number")
    return tank, cursor


# --------------------------------------------------------------------------- #
# Report parsers
# --------------------------------------------------------------------------- #

def parse_inventory_report(frame: bytes, verify: bool = True) -> InventoryReport:
    """Parse an i201 In-Tank Inventory Report."""
    _, cur = _open_frame(frame, FUNCTION_INVENTORY, verify)
    timestamp = cur.timestamp("timestamp")

    tanks = []
    while cur.remaining():
        tank = cur.decimal(2, "tank number")
        cur.take(INVENTORY_UNUSED_LEN, "unused")
        count = cur.hexadecimal(2, "field count")
        if count < INVENTORY_FIELD_COUNT:
            raise ProtocolError(f"tank {tank}: expected at least 7 fields, got {count}")
        values = cur.floats(count, f"tank {tank}")
        tanks.append(TankInventory(tank, *values[:INVENTORY_FIELD_COUNT]))

    return InventoryReport(FUNCTION_INVENTORY, timestamp, tuple(tanks))


def parse_status_report(frame: bytes, verify: bool = True) -> StatusReport:
    """Parse an i205 In-Tank Status Report.

    The manual shows a YYMMDDHHmm timestamp before the tank records, but some
    TLS-350 units omit it (body is just TTnnAA... records). Try the documented
    layout first and fall back to the timestamp-less one.
    """
    _, cur = _open_frame(frame, FUNCTION_STATUS, verify)
    body = cur.take(cur.remaining(), "status body")

    try:
        if len(body) < TIMESTAMP_LEN:
            raise ProtocolError("status body shorter than a timestamp")
        timestamp = parse_timestamp(body[:TIMESTAMP_LEN])
        return StatusReport(FUNCTION_STATUS, timestamp, _read_status_tanks(_Cursor(body[TIMESTAMP_LEN:])))
    except ProtocolError as documented_layout_error:
        try:
            return StatusReport(FUNCTION_STATUS, None, _read_status_tanks(_Cursor(body)))
        except ProtocolError:
            raise documented_layout_error from None


def _read_status_tanks(cur: _Cursor) -> tuple[TankStatus, ...]:
    tanks = []
    while cur.remaining():
        tank = cur.decimal(2, "tank number")
        count = cur.hexadecimal(2, "alarm count")
        alarms = tuple(
            Alarm(code, ALARM_NAMES.get(code, f"Unknown alarm {code}"))
            for code in (cur.decimal(2, "alarm code") for _ in range(count))
        )
        if count == 0 and cur.peek(2) == PLACEHOLDER_ALARM:
            # Real TLS-350 units send one dummy "00" alarm code for a tank with
            # no alarms. 00 is never a tank number, so this cannot be the next record.
            cur.take(2, "placeholder alarm")
        tanks.append(TankStatus(tank, alarms))
    return tuple(tanks)


def parse_delivery_report(frame: bytes, verify: bool = True) -> DeliveryReport:
    """Parse an i20C In-Tank Most Recent Delivery Report."""
    _, cur = _open_frame(frame, FUNCTION_DELIVERY, verify)
    timestamp = cur.timestamp("timestamp")

    tanks = []
    while cur.remaining():
        tank = cur.decimal(2, "tank number")
        product = cur.take(1, "product code")
        delivery_count = cur.decimal(2, "delivery count")
        deliveries = tuple(_read_delivery(cur, tank) for _ in range(delivery_count))
        if delivery_count == 0 and _placeholder_record_follows(cur):
            # Real TLS-350 units send one all-zero record (dates like "-001010800")
            # for a tank with no delivery on file, even though dd == 00.
            _read_delivery(cur, tank)
        tanks.append(TankDelivery(tank, product, deliveries))

    return DeliveryReport(FUNCTION_DELIVERY, timestamp, tuple(tanks))


def _placeholder_record_follows(cur: _Cursor) -> bool:
    """True when the next bytes cannot be a tank number, so must be a dummy record."""
    ahead = cur.peek(2)
    return len(ahead) == 2 and not ahead.isdigit()


def _read_delivery(cur: _Cursor, tank: int) -> Delivery:
    start = cur.timestamp("delivery start")
    end = cur.timestamp("delivery end")
    count = cur.hexadecimal(2, "field count")
    if count < DELIVERY_FIELD_COUNT:
        raise ProtocolError(f"tank {tank}: expected 10 delivery fields, got {count}")
    values = cur.floats(count, f"tank {tank} delivery")
    return Delivery(start, end, *values[:DELIVERY_FIELD_COUNT])
