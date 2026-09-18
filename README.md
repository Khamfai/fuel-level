# fuel-level

Reads tank data from a Veeder-Root TLS-350 gauge over RS-232, or straight from Pokcenser PWL-M200
magnetostrictive probes over RS-485 (no console needed), and pushes it to the fuel-api REST service.

**Full documentation (Thai): [docs/](docs/README.md)** — overview, server setup, Raspberry Pi setup, gauge protocol, API, troubleshooting.

| I want to... | Read |
|--------------|------|
| Install on a Raspberry Pi and pick console (RS-232) or probe (RS-485) mode | [docs/03-setup-raspberry-pi.md](docs/03-setup-raspberry-pi.md) |
| Wire a PWL-M200 probe straight to the Pi, find its tank number | [docs/07-probe-direct.md](docs/07-probe-direct.md) |
| Understand the TLS-350 commands and fields | [docs/04-gauge-protocol.md](docs/04-gauge-protocol.md) |
| Fix a probe or gauge that stays silent | [docs/06-troubleshooting.md](docs/06-troubleshooting.md), [docs/07-probe-direct.md](docs/07-probe-direct.md) |

## Layout

| File | Purpose |
|------|---------|
| `main.py` | CLI: heartbeat, poll the gauge, build JSON, POST it (or `--dry-run`) |
| `tls/protocol.py` | Frame building, checksum, parsers for 201 / 205 / 20C |
| `tls/transport.py` | Serial I/O (`TlsGauge`), port auto-detection |
| `tls/api.py` | `ApiClient` (device registration, heartbeat, log upload, Bearer auth) and `build_payload` |
| `pokcenser/protocol.py` | The console's ASCII poll/reply protocol (4800 baud, CRC-8), reverse-engineered from the wire |
| `pokcenser/probe.py` | `PokProbe`: polls probes by console tank number -> the same `InventoryReport` the TLS path produces |
| `probe_scan.py` | Field tool: discover which console tank numbers answer, print raw readings |
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

Flags fall back to env vars `TLS_SOURCE`, `TLS_PORT`, `TLS_BAUD`, `TLS_PROBE_ADDRS`, `TLS_API_URL`,
`TLS_API_KEY`, `TLS_SITE_ID`, `TLS_DEVICE_NAME`, `TLS_LAT`, `TLS_LNG`. Leave `TLS_BAUD` unset unless you
need to override the source's default (9600; 4800 for `pokcenser`).

## Probes without a console (`--source pokcenser`)

Pokcenser PWL-M200 / PWL-M300 probes can be wired straight to a USB-RS485 converter. The probes
that ship with a PWD-CM1 console do **not** answer the Modbus RTU described in the vendor's protocol
document; they speak the console's own ASCII protocol at **4800 8N1** (captured on the wire, see
[docs/07-probe-direct.md](docs/07-probe-direct.md)):

```text
poll   0xE0 + (tank - 1), 'B'                        e.g. E2 42 for console tank 3
reply  STX "1564.0:87.1:26.9" ETX crc8               fuel mm : water mm : temperature C
```

```bash
python3 probe_scan.py --find                              # poll tanks 1..8, list the ones that answer
python3 probe_scan.py --addrs 3 --loop 5                  # watch tank 3
python3 main.py --source pokcenser --probe-addrs 3 --dry-run
python3 main.py --source pokcenser --probe-addrs 3 --interval 60
```

- `--probe-addrs` are the **console tank numbers**; the payload's `tank` field matches the console screen.
- Only the `inventory` report exists (no alarms, no delivery history) and it is the default.
  `inventory.function` is `"pokcenser"`, `timestamp` is `null` (the probe has no clock).
- The probe reports `fuel_height`, `water_height` and `temperature` (mm / °C). It has no strapping table,
  so `fuel_volume`, `tc_volume`, `ullage` and `water_volume` are sent as `0`.
- A configured tank that does not answer is still sent, with every value `0` (the console shows the same for a
  tank without a probe), plus an error log. The cycle fails only when every configured tank is silent.
- Wiring (Pokcenser installation manual): white = RS-485 A, blue = RS-485 B, red = +24 V, black = power
  negative, yellow = shield. The probe needs 24 to 26 VDC; tie the supply negative to the converter's GND.
- Replies carry no address. **While a console is still wired to the same A/B pair it keeps polling, and
  its probes' answers can be mistaken for answers to ours** (`--find` then shows phantom tanks). For the
  final install leave the console on power only, or remove it, so the Pi is the only master.

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
      {"tank": 1, "fuel_volume": 1000.0, "tc_volume": 0.0, "ullage": 4000.0,
       "fuel_height": 48.25, "water_height": 0.0, "temperature": 76.1, "water_volume": 0.0}
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

Step-by-step guide (Thai), including how to choose between console and probe mode and how to
switch an existing install: **[docs/03-setup-raspberry-pi.md](docs/03-setup-raspberry-pi.md)**.

```bash
cd ~/fuel-level
sudo bash deploy/install.sh
```

This installs a systemd service (`deploy/fuel-level.service`) that starts the poller
after the network is up, polls every 60 s, and restarts it if it crashes.
Change settings in `/etc/default/fuel-level` (see `deploy/fuel-level.env.example`), then
`sudo systemctl restart fuel-level`. Logs: `journalctl -u fuel-level -f`.

Minimal config per mode:

```bash
# console TLS-350 over RS-232 (default): nothing to add
# PWL-M200 probe over RS-485, console tank 3:
TLS_SOURCE=pokcenser
TLS_PROBE_ADDRS=3
```

The service holds the serial port, so `sudo systemctl stop fuel-level` before running
`probe_scan.py` or a manual `main.py` by hand.
