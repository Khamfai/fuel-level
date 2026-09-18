# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python 3 poller that runs on a Raspberry Pi, reads tank reports from a Veeder-Root TLS-350 gauge over RS-232 (or straight from Pokcenser PWL-M200 probes over RS-485 with `--source pokcenser`, or `--source modbus` for probes that speak the vendor-documented Modbus), and POSTs them as JSON to the separate `fuel-api` service (Bun + Elysia, lives in another repo, default base URL `https://atg.moomou.com`). The only third-party dependency is `pyserial`; everything else, including the HTTP client, is standard library. The user-facing docs under `docs/` are in Thai.

## Commands

```bash
pip install pyserial                                   # the one dependency (requirements.txt)
python3 -m unittest discover -s tests                  # full suite (no pytest in this repo)
python3 -m unittest tests.test_protocol                # one module
python3 -m unittest tests.test_protocol.InventoryReportTest.test_parses_two_tanks   # one test
python3 -m unittest -v tests.test_main                 # verbose

python3 main.py --dry-run                              # read gauge, print payload, no network
python3 mock_server.py                                 # fake fuel-api on http://127.0.0.1:8000
python3 main.py --api-url http://127.0.0.1:8000        # poll once against the mock
python3 main.py --interval 60 --reports inventory,status,delivery
python3 main.py --source pokcenser --probe-addrs 3 --dry-run    # probe on RS-485, console tank 3
python3 probe_scan.py --find                           # which console tank numbers answer (1..8)
python3 probe_scan.py --proto modbus --scan            # hunt for a Modbus probe across baud/parity
```

Tests never touch real hardware or the network: `tests/test_transport.py` swaps in a `FakeSerial`, `tests/test_main.py` a `FakeGauge` passed through `run_once(open_gauge=...)`, and `tests/test_api.py` patches `urllib`. Keep new tests hermetic the same way.

There is no linter or formatter configured. Run from the repo root so that `tls` is importable.

## Architecture

Three layers, each importable without the one above it:

1. **`tls/protocol.py`**: pure bytes-to-dataclass code, no I/O. `build_command` produces `SOH + function + tank`; `parse_inventory_report` / `parse_status_report` / `parse_delivery_report` validate the `SOH fff TT YYMMDDHHmm ... && CCCC ETX` envelope through `_open_frame`, then walk the ASCII body with the `_Cursor` reader. Gauge floats are 8 hex chars of IEEE-754 single precision (`decode_float`). All report/tank types are frozen dataclasses. Errors are `ProtocolError` (subclass `ChecksumError`).
2. **`tls/transport.py`**: `TlsGauge`, a context manager over `serial.Serial`. `query` sends a command, reads until ETX, and retries once on `GaugeTimeout`. `inventory()` / `status()` / `last_delivery()` call `query` and hand the frame to the matching parser. `find_port` auto-detects the USB adapter by name hints.
3. **`tls/api.py`**: `ApiClient` (register device, heartbeat, post log; Bearer auth) and `build_payload`, which turns the dataclasses into the JSON document. `_to_json` rounds floats to 3 decimals and adds the derived `amount` to each delivery.

**Probe sources, same shape.** `pokcenser/protocol.py` is the protocol the PWD-CM1 console really uses with its probes, reverse-engineered from a wire capture: 4800 8N1, poll `0xE0+(tank-1)` `'B'`, reply `STX fuel:water:temp ETX crc8` (Dallas/Maxim CRC-8, brute-forced from three captured replies). It differs from the vendor's Modbus document entirely, so treat that document as untrustworthy for these units. `pokcenser/probe.py` wraps it in `PokProbe` (addresses are console tank numbers, echo and other masters' polls are skipped by searching for STX). Replies carry no address, so while a console shares the bus its probes' answers can be mistaken for ours.

`modbus/rtu.py` is a minimal Modbus RTU master (function 04 only, CRC-16, strips a looped-back echo, 2 s response timeout because the probe takes ~1 s to answer). `modbus/probe.py` wraps it in `PwlProbe`, which reads 16 input registers per probe address, decodes the byte-swapped IEEE floats, and returns the same `InventoryReport` / `TankInventory` the TLS parser does, so everything above the gauge layer is shared. Volumes are `0` (the probe has no strapping table), `timestamp` is `None`, `function` is `"pwl-m200"`. The protocol test vectors come from the Pokcenser "RS485 Protocol V2.0" document. `probe_scan.py` is the field tool for finding addresses and eyeballing readings.

`main.py` wires them: `parse_args` (every flag falls back to a `TLS_*` env var; `--baud` defaults per source, 4800 for pokcenser), then `main` loops `run_once`, which sends the heartbeat first, opens the device via `open_device(args)` (chosen by `--source`), calls `collect`, and posts. `--dry-run` sets `client` to `None` and prints instead of posting. For probe sources only the `inventory` report is allowed; `parse_args` rejects the others. A deployed Pi runs the poller as the `fuel-level` systemd service, which holds the serial port: stop it before running `probe_scan.py` or a manual poll.

## Behaviour worth knowing before changing things

- **Partial reads are fine, total failure is not.** `collect` skips a report that times out or fails to parse and still uploads the rest; it raises only when every requested report failed. The payload only contains the sections that were read.
- **Heartbeat is best effort.** A failed heartbeat is a warning and never blocks the poll. In `--interval` mode all errors (serial, timeout, protocol, API) are logged and the loop continues; in one-shot mode they produce exit code 1.
- **Gauge quirks the code deliberately handles.** The gauge drops a command sent within ~0.5 s of its previous reply (`COMMAND_GAP_S`). A `9999` function code means the gauge rejected the command. Some TLS-350 units omit the timestamp in the i205 status report, so `parse_status_report` tries the documented layout first and falls back to the timestamp-less one. Delivery reports may contain `00` placeholder records. Real captured frames live in `tests/test_protocol.py`; add one there when a new gauge quirk shows up.
- **API base URL, not endpoint.** `normalise_base_url` strips a legacy `/readings`, `/v1/logs` or `/api/v1/logs` suffix so old configs keep working; the client appends `/api/v1/...` itself. Every response is an envelope `{"success", "data", "error"}`; `ApiError.status` is the HTTP code or `None` when unreachable, and registration treats 409 as "already exists".
- **Payload field names are a contract with fuel-api.** Tank fields are `fuel_volume`, `fuel_height`, `water_height`, etc. (see the README for the full document). Renaming a dataclass field changes the JSON key, so coordinate with the server repo.
- **Device registration** needs `--device-name`, `--lat` and `--lng` together; `parse_args` rejects a partial set. Without a registered device the server answers 422 on every log.

## Deployment

`deploy/install.sh` (run with `sudo` on the Pi) installs `deploy/fuel-level.service` as a systemd unit, substituting the real user and path, and copies `deploy/fuel-level.env.example` to `/etc/default/fuel-level` only if it does not already exist. Machine-specific `deploy/*.env` files are gitignored. Live logs: `journalctl -u fuel-level -f`.
