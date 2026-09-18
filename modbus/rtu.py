"""Minimal Modbus RTU master over pyserial: function 04 (read input registers) only.

Frame layout:
    request   addr 04 start_hi start_lo count_hi count_lo crc_lo crc_hi
    response  addr 04 nbytes data... crc_lo crc_hi
    exception addr 84 code crc_lo crc_hi

CRC-16/MODBUS: poly 0xA001 (reflected 0x8005), init 0xFFFF, sent low byte first.
"""

from __future__ import annotations

import logging
import struct
import time

import serial

log = logging.getLogger(__name__)

FUNCTION_READ_INPUT_REGISTERS = 0x04
EXCEPTION_FLAG = 0x80
BROADCAST_ADDRESS = 0
MAX_ADDRESS = 0xFF
CRC_LEN = 2
RESPONSE_HEADER_LEN = 3  # addr, function, byte count
EXCEPTION_FRAME_LEN = 5  # addr, function|0x80, code, crc

DEFAULT_BAUD = 9600
DEFAULT_PARITY = "N"
PARITIES = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN, "O": serial.PARITY_ODD}
# The PWL-M200 needs ~1 s to acquire a reading before it answers.
DEFAULT_RESPONSE_TIMEOUT_S = 2.0
SERIAL_READ_TIMEOUT_S = 0.1


class ModbusError(Exception):
    """The reply is missing, malformed, or a Modbus exception."""


class CrcError(ModbusError):
    """The reply's CRC does not match its contents."""


class ModbusTimeout(ModbusError, TimeoutError):
    """No complete reply within the response timeout."""


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, "little")


def build_read_input_registers(address: int, start: int, count: int) -> bytes:
    if not BROADCAST_ADDRESS <= address <= MAX_ADDRESS:
        raise ValueError(f"modbus address must be 0..255, got {address}")
    body = struct.pack(">BBHH", address, FUNCTION_READ_INPUT_REGISTERS, start, count)
    return body + crc16(body)


def parse_read_response(frame: bytes, address: int, count: int) -> bytes:
    """Validate a function-04 reply and return its register bytes (2 per register)."""
    if len(frame) >= EXCEPTION_FRAME_LEN and frame[1] == FUNCTION_READ_INPUT_REGISTERS | EXCEPTION_FLAG:
        _check_crc(frame[:EXCEPTION_FRAME_LEN])
        raise ModbusError(f"probe {frame[0]} answered modbus exception {frame[2]}")

    expected_len = RESPONSE_HEADER_LEN + 2 * count + CRC_LEN
    if len(frame) < expected_len:
        raise ModbusError(f"short reply: {len(frame)} bytes, expected {expected_len}")
    frame = frame[:expected_len]
    _check_crc(frame)
    if frame[0] != address:
        raise ModbusError(f"reply from address {frame[0]}, expected {address}")
    if frame[1] != FUNCTION_READ_INPUT_REGISTERS:
        raise ModbusError(f"unexpected function code {frame[1]:#04x}")
    if frame[2] != 2 * count:
        raise ModbusError(f"byte count {frame[2]}, expected {2 * count}")
    return frame[RESPONSE_HEADER_LEN:-CRC_LEN]


def _check_crc(frame: bytes) -> None:
    if crc16(frame[:-CRC_LEN]) != frame[-CRC_LEN:]:
        raise CrcError(f"crc mismatch on {frame.hex(' ')}")


def decode_float_l(data: bytes) -> float:
    """Pokcenser type 10007 (IEEE_FLOAT_L): big-endian words, bytes swapped within each word."""
    if len(data) != 4:
        raise ValueError(f"need 4 bytes, got {len(data)}")
    return struct.unpack(">f", bytes((data[1], data[0], data[3], data[2])))[0]


class ModbusClient:
    """Context-managed serial master.

    with ModbusClient("/dev/ttyUSB0") as bus:
        regs = bus.read_input_registers(address=1, start=0, count=16)
    """

    def __init__(
        self,
        port: str,
        baud: int = DEFAULT_BAUD,
        response_timeout: float = DEFAULT_RESPONSE_TIMEOUT_S,
        parity: str = DEFAULT_PARITY,
    ):
        if parity not in PARITIES:
            raise ValueError(f"parity must be one of {', '.join(PARITIES)}, got {parity!r}")
        self._port = port
        self._baud = baud
        self._parity = parity
        self._response_timeout = response_timeout
        self._ser: serial.Serial | None = None

    def __enter__(self) -> "ModbusClient":
        self._ser = serial.Serial(
            self._port,
            self._baud,
            bytesize=serial.EIGHTBITS,
            parity=PARITIES[self._parity],
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_READ_TIMEOUT_S,
        )
        return self

    def __exit__(self, *exc) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def read_input_registers(self, address: int, start: int, count: int) -> bytes:
        if self._ser is None:
            raise RuntimeError("use ModbusClient inside a 'with' block")
        request = build_read_input_registers(address, start, count)
        expected_len = RESPONSE_HEADER_LEN + 2 * count + CRC_LEN

        self._ser.reset_input_buffer()
        self._ser.write(request)
        raw = self._read_frame(expected_len, echo=request)
        log.debug("addr %d raw reply (%d bytes): %s", address, len(raw), raw.hex(" "))
        return parse_read_response(raw, address, count)

    def _read_frame(self, expected_len: int, echo: bytes) -> bytes:
        """Collect bytes until a full reply (or exception frame) is in, dropping a looped-back echo.

        The echo can be longer than the reply (an 8-byte request, a 7-byte one-register reply),
        so a buffer that is still a prefix of the echo is never treated as a finished reply.
        """
        assert self._ser is not None
        deadline = time.monotonic() + self._response_timeout
        want = max(expected_len, len(echo))
        buf = b""
        while time.monotonic() < deadline:
            chunk = self._ser.read(max(want - len(buf), 1))
            if chunk:
                buf += chunk
                if buf.startswith(echo):
                    buf = buf[len(echo):]
            if _could_be_echo(buf, echo):
                continue
            if _is_complete(buf, expected_len):
                return buf
        if buf and not _could_be_echo(buf, echo) and _is_complete(buf, expected_len):
            return buf
        raise ModbusTimeout(
            f"no reply within {self._response_timeout:.1f}s ({len(buf)} bytes received)"
        )


def _could_be_echo(buf: bytes, echo: bytes) -> bool:
    """True while the buffer is a (non-empty) proper prefix of our own request."""
    return 0 < len(buf) < len(echo) and echo.startswith(buf)


def _is_complete(buf: bytes, expected_len: int) -> bool:
    if len(buf) >= expected_len:
        return True
    return len(buf) >= EXCEPTION_FRAME_LEN and bool(buf[1] & EXCEPTION_FLAG)
