"""Field tool for PWL-M200 probes on a USB-RS485 converter: find an address, print raw readings.

Console-protocol probes (what a PWD-CM1 ships with, 4800 baud), the default:
    python3 probe_scan.py --find                  # poll console tank numbers 1..8, list who answers
    python3 probe_scan.py --addrs 3               # read tank 3 once
    python3 probe_scan.py --addrs 3 --loop 5      # re-read every 5 s (Ctrl-C to stop)

Modbus RTU probes (the vendor's documented protocol, 9600 baud):
    python3 probe_scan.py --proto modbus --find   # one probe on the bus: ask it its address
    python3 probe_scan.py --proto modbus --scan   # silent probe: try every baud/parity until it answers
    python3 probe_scan.py --proto modbus --addrs 1,2,3

Exit status is the number of probes that failed to answer.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Callable, Iterable, Optional

from modbus.probe import decode_reading
from modbus.rtu import BROADCAST_ADDRESS, DEFAULT_BAUD, DEFAULT_PARITY, PARITIES, ModbusClient, ModbusError
from pokcenser.probe import DEFAULT_BAUD as POKCENSER_BAUD, PokProbe
from tls.protocol import ProtocolError
from tls.transport import find_port

PROTOCOLS = ("pokcenser", "modbus")
POK_FIND_TANKS = range(1, 9)

ADDRESS_REGISTER = 0x20  # broadcast read returns the probe's own address (protocol doc §3.2)
DATA_REGISTER_START = 0x0000
DATA_REGISTER_COUNT = 16
SCAN_BAUDS = (9600, 19200, 4800, 38400, 2400, 57600, 115200, 1200)
SCAN_TIMEOUT_S = 1.5  # the probe answers within ~1 s when it understands us at all


def find_address(bus) -> int:
    """Only valid with a single probe on the bus (broadcast)."""
    data = bus.read_input_registers(BROADCAST_ADDRESS, ADDRESS_REGISTER, 1)
    return int.from_bytes(data[:2], "big")


def scan_settings(
    open_bus: Callable[[int, str], ModbusClient],
    bauds: Iterable[int] = SCAN_BAUDS,
    parities: Iterable[str] = tuple(PARITIES),
) -> Optional[tuple[int, str, int]]:
    """Try each baud/parity with the broadcast address query; return (baud, parity, address) or None."""
    parities = tuple(parities)
    for baud in bauds:
        for parity in parities:
            print(f"trying {baud} 8{parity}1 ...", end=" ", flush=True)
            with open_bus(baud, parity) as bus:
                try:
                    address = find_address(bus)
                except ModbusError as exc:
                    print(f"no ({exc})")
                    continue
            print(f"answered: address {address}")
            return baud, parity, address
    return None


def print_readings(bus, addresses: list[int]) -> int:
    """One line per address; returns how many failed."""
    failures = 0
    for address in addresses:
        try:
            r = decode_reading(bus.read_input_registers(address, DATA_REGISTER_START, DATA_REGISTER_COUNT))
        except (ModbusError, ProtocolError) as exc:
            failures += 1
            print(f"addr {address:3d}: FAILED {exc}")
            continue
        points = " ".join(f"{t:.1f}" for t in r.point_temperatures_c)
        print(
            f"addr {address:3d}: fuel {r.fuel_mm:8.1f} mm  water {r.water_mm:7.1f} mm  "
            f"temp {r.temperature_c:5.2f} C  points [{points}]"
        )
    return failures


def find_pok_tanks(probe, tanks: Iterable[int] = POK_FIND_TANKS) -> list[int]:
    """Poll each console tank number; return the ones that answered."""
    found = []
    for tank in tanks:
        try:
            r = probe.read(tank)
        except ProtocolError as exc:
            print(f"tank {tank}: silent ({exc})")
            continue
        print(f"tank {tank}: answers  fuel {r.fuel_mm:.1f} mm  water {r.water_mm:.1f} mm  temp {r.temperature_c:.1f} C")
        found.append(tank)
    return found


def print_pok_readings(probe, tanks: list[int]) -> int:
    failures = 0
    for tank in tanks:
        try:
            r = probe.read(tank)
        except ProtocolError as exc:
            failures += 1
            print(f"tank {tank:2d}: FAILED {exc}")
            continue
        print(f"tank {tank:2d}: fuel {r.fuel_mm:8.1f} mm  water {r.water_mm:7.1f} mm  temp {r.temperature_c:5.1f} C")
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--proto", choices=PROTOCOLS, default="pokcenser", help="probe protocol (default: %(default)s)")
    p.add_argument("--port", help="serial device; default: first USB serial adapter")
    p.add_argument("--baud", type=int, default=None, help="default: 4800 for pokcenser, 9600 for modbus")
    p.add_argument("--parity", choices=tuple(PARITIES), default=DEFAULT_PARITY)
    p.add_argument("--addrs", default="1", help="comma list of probe addresses to read")
    p.add_argument("--find", action="store_true", help="pokcenser: poll tanks 1..8; modbus: broadcast-query the single probe")
    p.add_argument("--scan", action="store_true", help="modbus: try every baud/parity with the broadcast query")
    p.add_argument("--loop", type=float, default=0, help="seconds between re-reads; 0 = once")
    args = p.parse_args(argv)
    if args.baud is None:
        args.baud = POKCENSER_BAUD if args.proto == "pokcenser" else DEFAULT_BAUD
    if args.proto == "pokcenser" and args.scan:
        p.error("--scan is for --proto modbus; pokcenser probes are always 4800 8N1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    port = args.port or find_port()
    addresses = [int(a) for a in args.addrs.split(",") if a.strip()]
    if args.proto == "pokcenser":
        print(f"port {port}, {args.baud} 8N1, console protocol")
        return _main_pokcenser(port, args, addresses)
    print(f"port {port}, {args.baud} 8{args.parity}1, modbus")
    if args.scan:
        found = scan_settings(lambda baud, parity: ModbusClient(port, baud, SCAN_TIMEOUT_S, parity))
        if found is None:
            print("no answer at any baud/parity: check A/B wiring and the GND link", file=sys.stderr)
            return 1
        baud, parity, address = found
        print(f"use: --baud {baud} --parity {parity} --addrs {address}")
        return 0
    with ModbusClient(port, args.baud, parity=args.parity) as bus:
        if args.find:
            try:
                print(f"probe address: {find_address(bus)}")
                return 0
            except ModbusError as exc:
                print(f"no answer to broadcast: {exc}", file=sys.stderr)
                return 1
        while True:
            failures = print_readings(bus, addresses)
            if not args.loop:
                return failures
            time.sleep(args.loop)


def _main_pokcenser(port: str, args: argparse.Namespace, tanks: list[int]) -> int:
    with PokProbe(port, args.baud, addresses=tanks) as probe:
        if args.find:
            found = find_pok_tanks(probe)
            print(f"use: --probe-addrs {','.join(map(str, found))}" if found else "no tank answered", file=sys.stderr)
            return 0 if found else 1
        while True:
            failures = print_pok_readings(probe, tanks)
            if not args.loop:
                return failures
            time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
