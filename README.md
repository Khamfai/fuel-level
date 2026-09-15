# fuel-level

Reads tank data from a Veeder-Root TLS-350 gauge over RS-232 and pushes it to a REST API.

## Layout

| File | Purpose |
|------|---------|
| `main.py` | CLI: poll the gauge, build JSON, POST it (or `--dry-run`) |
| `tls/protocol.py` | Frame building, checksum, parsers for 201 / 205 / 20C |
| `tls/transport.py` | Serial I/O (`TlsGauge`), port auto-detection |
| `tls/api.py` | `ApiClient` (POST JSON, Bearer auth) and `build_payload` |
| `mock_server.py` | Local stand-in for the not-yet-built API |
| `tests/` | `python3 -m unittest discover -s tests` |

## Usage

```bash
pip install pyserial
python3 main.py --dry-run                                   # print what would be sent
python3 main.py --api-url http://127.0.0.1:8000/readings    # one shot
python3 main.py --interval 60 --reports inventory,status,delivery
```

Flags fall back to env vars `TLS_PORT`, `TLS_BAUD`, `TLS_API_URL`, `TLS_API_KEY`, `TLS_SITE_ID`.

## Payload sent to the API

`POST {api-url}` with `Content-Type: application/json` and, when a key is set,
`Authorization: Bearer <key>`. Sections are present only for the reports requested.

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
