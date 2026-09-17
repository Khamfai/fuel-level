"""Pokcenser PWL-M200 / PWL-M300 magnetostrictive probe over Modbus RTU.

Each probe is one Modbus slave and measures one tank. Function 04 from
register 0x0000 returns eight IEEE_FLOAT_L values (see modbus.rtu):
    0-1 fuel level mm   2-3 water level mm   4-5 average fuel temperature C
    6-15 point temperatures A..E in C (unused points read 0)

The probe has no clock, no strapping table and no alarms, so the report it
produces carries no timestamp and zero volumes; volume is the server's job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from modbus.rtu import DEFAULT_BAUD, DEFAULT_RESPONSE_TIMEOUT_S, ModbusClient, ModbusError, decode_float_l
from tls.protocol import InventoryReport, ProtocolError, TankInventory

log = logging.getLogger(__name__)

PROBE_FUNCTION = "pwl-m200"
REGISTER_START = 0x0000
REGISTER_COUNT = 16
FLOAT_LEN = 4
POINT_TEMPERATURE_COUNT = 5


@dataclass(frozen=True)
class ProbeReading:
    fuel_mm: float
    water_mm: float
    temperature_c: float
    point_temperatures_c: tuple[float, ...]


def decode_reading(data: bytes) -> ProbeReading:
    """Turn the 32 register bytes into a reading."""
    if len(data) != 2 * REGISTER_COUNT:
        raise ProtocolError(f"probe returned {len(data)} bytes, expected {2 * REGISTER_COUNT}")
    values = [decode_float_l(data[i: i + FLOAT_LEN]) for i in range(0, len(data), FLOAT_LEN)]
    fuel, water, temperature, *points = values
    return ProbeReading(fuel, water, temperature, tuple(points[:POINT_TEMPERATURE_COUNT]))


class PwlProbe:
    """Context-managed reader for one or more probes on the same RS-485 bus.

    with PwlProbe("/dev/ttyUSB0", addresses=[1, 2]) as probe:
        report = probe.inventory()   # tank 1 = address 1, tank 2 = address 2
    """

    def __init__(
        self,
        port: str,
        baud: int = DEFAULT_BAUD,
        addresses: Sequence[int] = (1,),
        response_timeout: float = DEFAULT_RESPONSE_TIMEOUT_S,
    ):
        self._addresses = tuple(addresses)
        self._client = ModbusClient(port, baud, response_timeout)
        self._bus: Optional[ModbusClient] = None

    def __enter__(self) -> "PwlProbe":
        self._bus = self._client.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self._client.__exit__(*exc)
        self._bus = None

    def read(self, address: int) -> ProbeReading:
        if self._bus is None:
            raise RuntimeError("use PwlProbe inside a 'with' block")
        data = self._bus.read_input_registers(address, REGISTER_START, REGISTER_COUNT)
        return decode_reading(data)

    def inventory(self, tank: str = "00") -> InventoryReport:
        """Read every configured probe; tank N is the Nth address. Skips probes that fail."""
        tanks: list[TankInventory] = []
        failures: list[Exception] = []
        for number, address in enumerate(self._addresses, start=1):
            try:
                reading = self.read(address)
            except (ModbusError, ProtocolError) as exc:
                log.error("probe at address %d (tank %d) failed, skipping it: %s", address, number, exc)
                failures.append(exc)
                continue
            tanks.append(_to_tank(number, reading))
        if not tanks:
            raise ProtocolError(
                f"all {len(self._addresses)} probe(s) failed; last error: {failures[-1]}"
            )
        return InventoryReport(PROBE_FUNCTION, None, tuple(tanks))


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
