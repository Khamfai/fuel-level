# fuel-level

Reads tank data from a Veeder-Root TLS-350 gauge over RS-232 and pushes it to the fuel-api REST service.

**Full documentation (Thai): [docs/](docs/README.md)** — overview, server setup, Raspberry Pi setup, gauge protocol, API, troubleshooting.

## Layout

| File | Purpose |
|------|---------|
| `main.py` | CLI: heartbeat, poll the gauge, build JSON, POST it (or `--dry-run`) |
| `tls/protocol.py` | Frame building, checksum, parsers for 201 / 205 / 20C |
| `tls/transport.py` | Serial I/O (`TlsGauge`), port auto-detection |
| `tls/api.py` | `ApiClient` (device registration, heartbeat, log upload, Bearer auth) and `build_payload` |
| `mock_server.py` | Zero-dependency stand-in for fuel-api that prints what it receives |
| `tests/` | `python3 -m unittest discover -s tests` |

The server side lives in the separate `fuel-api` repository (Bun + Elysia + Prisma on MariaDB/MySQL).

## Usage

```bash
pip install pyserial
python3 main.py --dry-run                                   # print what would be sent
python3 main.py --device-name "Station 7" --lat 13.75 --lng 100.5   # register this site's device, then poll once
python3 main.py                                             # one shot to the default server
python3 main.py --interval 60 --reports inventory,status,delivery
```

Flags fall back to env vars `TLS_PORT`, `TLS_BAUD`, `TLS_API_URL`, `TLS_API_KEY`, `TLS_SITE_ID`,
`TLS_DEVICE_NAME`, `TLS_LAT`, `TLS_LNG`.

`--api-url` is the API **base URL** (default `https://atg.moomou.com`);
the endpoints below are appended to it. An old value ending in `/readings`, `/v1/logs` or `/api/v1/logs` still works,
the path is stripped.

## What one poll cycle does

1. `POST {base}/api/v1/devices/{site_id}/heartbeat` — tells the server the device is alive, even if the
   gauge turns out to be unreachable. A failed heartbeat is logged as a warning and never stops the poll.
   Disable with `--no-heartbeat`.
2. Read the requested reports from the gauge.
3. `POST {base}/api/v1/logs` with the JSON below. Accepted logs also count as presence on the server.

The server only accepts logs for a registered device. Register once with `--device-name/--lat/--lng`
(or the matching env vars); running it again is harmless, the server answers 409 and the poller moves on.
Without a device every upload fails with `HTTP 422 ... unknown site_id`.

Every request carries `Content-Type: application/json` and, when a key is set,
`Authorization: Bearer <key>`. Responses are envelopes: `{"success": true, "data": ...}` or
`{"success": false, "data": null, "error": {"message": "...", "details": [...]}}`; the poller logs the
`message` and `details` on failure.

## Log payload

Sections are present only for the reports requested.

```json
{
  "site_id": "default",
  "collected_at": "2026-09-15T04:30:00+00:00",
  "inventory": {
    "function": "i201",
    "timestamp": "2026-09-15T12:30:00",
    "tanks": [
      {"tank": 1, "volume": 1000.0, "tc_volume": 0.0, "ullage": 4000.0,
       "height": 48.25, "water": 0.0, "temperature": 76.1, "water_volume": 0.0}
    ]
  },
  "status": {
    "function": "i205",
    "timestamp": "2026-09-15T12:30:00",
    "tanks": [
      {"tank": 1, "alarms": [{"code": 5, "name": "Tank Low Product Alarm"}]}
    ]
  },
  "delivery": {
    "function": "i20C",
    "timestamp": "2026-09-15T12:30:00",
    "tanks": [
      {"tank": 1, "product_code": "R", "deliveries": [
        {"start_time": "2026-09-14T15:05:00", "end_time": "2026-09-14T15:14:00",
         "start_volume": 1244.0, "end_volume": 3231.0, "amount": 1987.0,
         "start_tc_volume": 1231.0, "end_tc_volume": 3194.0,
         "start_water": 0.0, "end_water": 0.0, "start_temp": 73.89, "end_temp": 76.14,
         "start_height": 24.4, "end_height": 48.27}
      ]}
    ]
  }
}
```

Units are whatever the gauge is configured for (gallons/inches/°F or litres/mm/°C).
`timestamp` is the gauge clock (no timezone); `collected_at` is the host clock in UTC.

## Run at boot on the Raspberry Pi

```bash
cd ~/fuel-level
sudo bash deploy/install.sh
```

This installs a systemd service (`deploy/fuel-level.service`) that starts the poller
after the network is up, polls every 60 s, and restarts it if it crashes.
Change settings in `/etc/default/fuel-level` (see `deploy/fuel-level.env.example`), then
`sudo systemctl restart fuel-level`. Logs: `journalctl -u fuel-level -f`.
