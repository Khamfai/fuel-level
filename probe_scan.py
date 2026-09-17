"""Field tool for PWL-M200 probes on a USB-RS485 converter: find an address, print raw readings.

    python3 probe_scan.py --find                  # one probe on the bus: ask it its address
    python3 probe_scan.py --addrs 1,2,3           # read each probe once and print the values
    python3 probe_scan.py --addrs 1 --loop 5      # re-read every 5 s (Ctrl-C to stop)

Exit status is the number of probes that failed to answer.
"""

from __future__ import annotations

import argparse
import sys
import time

from modbus.probe import decode_reading
from modbus.rtu import BROADCAST_ADDRESS, DEFAULT_BAUD, ModbusClient, ModbusError
from tls.protocol import ProtocolError
from tls.transport import find_port

ADDRESS_REGISTER = 0x20  # broadcast read returns the probe's own address (protocol doc §3.2)
DATA_REGISTER_START = 0x0000
DATA_REGISTER_COUNT = 16


def find_address(bus) -> int:
    """Only valid with a single probe on the bus (broadcast)."""
    data = bus.read_input_registers(BROADCAST_ADDRESS, ADDRESS_REGISTER, 1)
    return int.from_bytes(data[:2], "big")


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="serial device; default: first USB serial adapter")
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    p.add_argument("--addrs", default="1", help="comma list of probe addresses to read")
    p.add_argument("--find", action="store_true", help="broadcast-query the single connected probe for its address")
    p.add_argument("--loop", type=float, default=0, help="seconds between re-reads; 0 = once")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    port = args.port or find_port()
    addresses = [int(a) for a in args.addrs.split(",") if a.strip()]
    with ModbusClient(port, args.baud) as bus:
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


if __name__ == "__main__":
    sys.exit(main())
