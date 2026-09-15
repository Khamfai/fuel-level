"""Poll a Veeder-Root TLS gauge over serial and push the readings to a REST API.

Examples:
    python3 main.py --dry-run                       # print JSON, no upload
    python3 main.py --api-url http://host/readings  # one shot
    python3 main.py --interval 60                   # poll forever, every 60 s

Environment variables (overridden by flags): TLS_PORT, TLS_BAUD, TLS_API_URL,
TLS_API_KEY, TLS_SITE_ID.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any

import serial

from tls.api import ApiClient, ApiError, build_payload
from tls.protocol import ProtocolError
from tls.transport import DEFAULT_BAUD, GaugeTimeout, TlsGauge, find_port

REPORTS = ("inventory", "status", "delivery")
log = logging.getLogger("fuel-level")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", default=os.environ.get("TLS_PORT"), help="serial device, e.g. /dev/cu.usbserial-1420")
    p.add_argument("--baud", type=int, default=int(os.environ.get("TLS_BAUD", DEFAULT_BAUD)))
    p.add_argument("--tank", default="00", help="tank number, 00 = all tanks")
    p.add_argument("--reports", default="inventory,status", help=f"comma list of {', '.join(REPORTS)}")
    p.add_argument("--api-url", default=os.environ.get("TLS_API_URL"), help="POST endpoint for readings")
    p.add_argument("--api-key", default=os.environ.get("TLS_API_KEY"), help="sent as Bearer token")
    p.add_argument("--site-id", default=os.environ.get("TLS_SITE_ID", "default"))
    p.add_argument("--interval", type=float, default=0, help="seconds between polls; 0 = run once")
    p.add_argument("--dry-run", action="store_true", help="print the payload instead of posting it")
    p.add_argument("--no-verify-checksum", action="store_true", help="skip response checksum check")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    args.reports = [r.strip() for r in args.reports.split(",") if r.strip()]
    unknown = [r for r in args.reports if r not in REPORTS]
    if unknown:
        p.error(f"unknown report(s): {', '.join(unknown)}")
    if not args.dry_run and not args.api_url:
        p.error("--api-url (or TLS_API_URL) is required unless --dry-run is given")
    return args


def collect(gauge: TlsGauge, reports: list[str], tank: str, site_id: str) -> dict[str, Any]:
    """Read the requested reports from the gauge and build the upload payload."""
    readers = {
        "inventory": gauge.inventory,
        "status": gauge.status,
        "delivery": gauge.last_delivery,
    }
    results = {name: readers[name](tank) for name in reports}
    return build_payload(site_id, **results)


def run_once(args: argparse.Namespace, client: ApiClient | None) -> None:
    with TlsGauge(args.port, args.baud, verify_checksum=not args.no_verify_checksum) as gauge:
        payload = collect(gauge, args.reports, args.tank, args.site_id)

    if client is None:
        print(json.dumps(payload, indent=2))
        return
    status = client.post(payload)
    log.info("posted %s report(s) to %s -> HTTP %s", len(args.reports), args.api_url, status)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    port = args.port or find_port()
    args.port = port
    client = None if args.dry_run else ApiClient(args.api_url, args.api_key)
    log.info("gauge on %s @ %d baud, tank %s, reports %s", port, args.baud, args.tank, ",".join(args.reports))

    while True:
        try:
            run_once(args, client)
        except (serial.SerialException, GaugeTimeout, ProtocolError, ApiError) as exc:
            log.error("%s", exc)
            if not args.interval:
                return 1
        if not args.interval:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
