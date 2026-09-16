"""Poll a Veeder-Root TLS gauge over serial and push the readings to fuel-api.

Each cycle sends a heartbeat (POST /api/v1/devices/{site}/heartbeat) so the server can
tell "device alive" from "gauge reporting", then reads the gauge and POSTs the
report to /api/v1/logs. The site's device must exist on the server first; pass
--device-name/--lat/--lng once to register it.

Examples:
    python3 main.py --dry-run                        # print JSON, no upload
    python3 main.py                                  # one shot to the default server
    python3 main.py --interval 60                    # poll forever, every 60 s
    python3 main.py --api-url https://other.example  # different server (base URL)
    python3 main.py --device-name "Station 7" --lat 13.75 --lng 100.5   # register, then poll

Environment variables (overridden by flags): TLS_PORT, TLS_BAUD, TLS_API_URL,
TLS_API_KEY, TLS_SITE_ID, TLS_DEVICE_NAME, TLS_LAT, TLS_LNG.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Callable

import serial

from tls.api import ApiClient, ApiError, build_payload
from tls.protocol import ProtocolError
from tls.transport import DEFAULT_BAUD, GaugeTimeout, TlsGauge, find_port

REPORTS = ("inventory", "status", "delivery")
DEFAULT_API_URL = "https://atg.moomou.com"  # fuel-api on Dokploy
log = logging.getLogger("fuel-level")


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--port",
        default=os.environ.get("TLS_PORT"),
        help="serial device, e.g. /dev/cu.usbserial-1420",
    )
    p.add_argument(
        "--baud", type=int, default=int(os.environ.get("TLS_BAUD", DEFAULT_BAUD))
    )
    p.add_argument("--tank", default="00", help="tank number, 00 = all tanks")
    p.add_argument(
        "--reports",
        default="inventory,status",
        help=f"comma list of {', '.join(REPORTS)}",
    )
    p.add_argument(
        "--api-url",
        default=os.environ.get("TLS_API_URL", DEFAULT_API_URL),
        help="fuel-api base URL; a trailing .../readings, .../v1/logs or .../api/v1/logs path is stripped (default: %(default)s)",
    )
    p.add_argument(
        "--api-key", default=os.environ.get("TLS_API_KEY"), help="sent as Bearer token"
    )
    p.add_argument("--site-id", default=os.environ.get("TLS_SITE_ID", "default"))
    p.add_argument(
        "--device-name",
        default=os.environ.get("TLS_DEVICE_NAME"),
        help="with --lat/--lng: register the device at startup",
    )
    p.add_argument(
        "--lat",
        type=float,
        default=_env_float("TLS_LAT"),
        help="device latitude, decimal degrees",
    )
    p.add_argument(
        "--lng",
        type=float,
        default=_env_float("TLS_LNG"),
        help="device longitude, decimal degrees",
    )
    p.add_argument(
        "--interval", type=float, default=0, help="seconds between polls; 0 = run once"
    )
    p.add_argument(
        "--no-heartbeat",
        action="store_true",
        help="do not POST a heartbeat before each poll",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print the payload instead of posting it"
    )
    p.add_argument(
        "--no-verify-checksum", action="store_true", help="skip response checksum check"
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    args.reports = [r.strip() for r in args.reports.split(",") if r.strip()]
    unknown = [r for r in args.reports if r not in REPORTS]
    if unknown:
        p.error(f"unknown report(s): {', '.join(unknown)}")

    given = [
        name
        for name, value in (
            ("--device-name", args.device_name),
            ("--lat", args.lat),
            ("--lng", args.lng),
        )
        if value is not None
    ]
    if given and len(given) != 3:
        p.error(
            "--device-name, --lat and --lng must be given together to register the device"
        )
    return args


def collect(
    gauge: TlsGauge, reports: list[str], tank: str, site_id: str
) -> dict[str, Any]:
    """Read the requested reports from the gauge and build the upload payload."""
    readers = {
        "inventory": gauge.inventory,
        "status": gauge.status,
        "delivery": gauge.last_delivery,
    }
    results: dict[str, Any] = {}
    failures: list[Exception] = []
    for name in reports:
        try:
            results[name] = readers[name](tank)
        except (GaugeTimeout, ProtocolError) as exc:
            log.error("%s report failed, skipping it: %s", name, exc)
            failures.append(exc)
    if not results:
        raise ProtocolError(
            f"all {len(reports)} report(s) failed; last error: {failures[-1]}"
        )
    return build_payload(site_id, **results)


def send_heartbeat(client: ApiClient) -> None:
    """Best effort: a failed heartbeat is logged but never stops the poll."""
    try:
        online = client.heartbeat()
        log.debug("heartbeat ok, server says online=%s", online)
    except ApiError as exc:
        log.warning("heartbeat failed: %s", exc)


def run_once(
    args: argparse.Namespace,
    client: ApiClient | None,
    open_gauge: Callable[..., Any] = TlsGauge,
) -> None:
    """One poll cycle: heartbeat first (so a dead gauge still shows the device alive), then read and post."""
    if client is not None and not args.no_heartbeat:
        send_heartbeat(client)

    with open_gauge(
        args.port, args.baud, verify_checksum=not args.no_verify_checksum
    ) as gauge:
        payload = collect(gauge, args.reports, args.tank, args.site_id)

    if client is None:
        print(json.dumps(payload, indent=2))
        return
    status = client.post_log(payload)
    log.info(
        "posted %s report(s) to %s -> HTTP %s",
        len(args.reports),
        client.logs_url,
        status,
    )


def register_device(args: argparse.Namespace, client: ApiClient) -> None:
    outcome = client.register_device(args.device_name, args.lat, args.lng)
    log.info(
        "device %s for site %s (%s, %s)",
        outcome,
        args.site_id,
        args.device_name,
        f"{args.lat},{args.lng}",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    port = args.port or find_port()
    args.port = port
    client = (
        None if args.dry_run else ApiClient(args.api_url, args.site_id, args.api_key)
    )
    log.info(
        "gauge on %s @ %d baud, tank %s, reports %s",
        port,
        args.baud,
        args.tank,
        ",".join(args.reports),
    )
    if client is not None:
        log.info(
            "api %s, site %s, heartbeat %s",
            client.base_url,
            args.site_id,
            "off" if args.no_heartbeat else "on",
        )
        if args.device_name is not None:
            try:
                register_device(args, client)
            except ApiError as exc:
                log.error("device registration failed: %s", exc)
                if not args.interval:
                    return 1

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
