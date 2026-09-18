"""Field tool for PWL-M200 probes on a USB-RS485 converter: find which tanks answer, print raw readings.

    python3 probe_scan.py --find                  # poll console tank numbers 1..8, list who answers
    python3 probe_scan.py --addrs 3               # read tank 3 once
    python3 probe_scan.py --addrs 3 --loop 5      # re-read every 5 s (Ctrl-C to stop)

Stop the fuel-level service first; it holds the serial port.
Exit status is the number of tanks that failed to answer.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Iterable

from pokcenser.probe import DEFAULT_BAUD, PokProbe
from tls.protocol import ProtocolError
from tls.transport import find_port

FIND_TANKS = range(1, 9)


def find_tanks(probe, tanks: Iterable[int] = FIND_TANKS) -> list[int]:
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


def print_readings(probe, tanks: list[int]) -> int:
    """One line per tank; returns how many failed."""
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
    p.add_argument("--port", help="serial device; default: first USB serial adapter")
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    p.add_argument("--addrs", default="1", help="comma list of console tank numbers to read")
    p.add_argument("--find", action="store_true", help="poll tanks 1..8 and list the ones that answer")
    p.add_argument("--loop", type=float, default=0, help="seconds between re-reads; 0 = once")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    port = args.port or find_port()
    print(f"port {port}, {args.baud} 8N1")
    tanks = [int(a) for a in args.addrs.split(",") if a.strip()]
    with PokProbe(port, args.baud, addresses=tanks) as probe:
        if args.find:
            found = find_tanks(probe)
            print(f"use: --probe-addrs {','.join(map(str, found))}" if found else "no tank answered", file=sys.stderr)
            return 0 if found else 1
        while True:
            failures = print_readings(probe, tanks)
            if not args.loop:
                return failures
            time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
