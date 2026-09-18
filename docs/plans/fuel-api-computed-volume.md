# Plan for fuel-api: compute tank volumes on the server from probe heights

**Audience:** the agent working in the `fuel-api` repository (Bun + Elysia + Prisma, MariaDB/MySQL).
**Requested by:** the fuel-level (Raspberry Pi poller) side. The Pi needs **no change** for this plan.
**Status of inputs:** tank 3 at site `station-2` has diameter 2040 mm; its length is still being measured.

## 1. Why

The Pi now reads Pokcenser PWL-M200 probes directly (`inventory.function == "pokcenser"`). A probe only
measures `fuel_height`, `water_height` (mm) and `temperature` (°C). It has no strapping table, so the Pi
sends `fuel_volume`, `water_volume`, `ullage`, `tc_volume` as `0`.

The old path (`inventory.function == "i201"`, Veeder-Root console) still sends the console's own volumes.
Those come from a strapping table typed into the console, and for this site that table is wrong
(at 87.1 mm of water the console claims 892 L; the tank's geometry gives about 296 L).

Decision: the **server** derives volumes from heights and per-tank geometry **once, when the station's
POST arrives**, stores the result in its own column next to the raw payload, and returns that stored
result on every read (no recomputation per query). Geometry lives on the server so it can be corrected
from the admin page; when it changes, a recompute job rewrites the stored results for that tank's
history, with no Pi redeploys.

**Hard rule: computed values never overwrite console values.** The volumes the console reported
(`payload.inventory.tanks[].fuel_volume`, `tc_volume`, `ullage`, `water_volume`) stay exactly as received,
both in the database and in every API response. The derived numbers go into a **new, separate key**
(`computed`, section 3.4). A consumer that wants the console's numbers reads `payload`; one that wants the
geometry-based numbers reads `computed`; both are always available side by side and neither replaces the other.

## 2. Data already available

Every log row stores the Pi's payload verbatim (see `POST /api/v1/logs`). Per tank:

```json
{"tank": 3, "fuel_height": 1564.0, "water_height": 87.1, "temperature": 26.9,
 "fuel_volume": 0.0, "tc_volume": 0.0, "ullage": 0.0, "water_volume": 0.0}
```

- `fuel_height` and `water_height` are both measured **from the tank bottom**, in mm. Water sits under the fuel.
- `inventory.function` is `"pokcenser"` (probe, volumes are 0) or `"i201"` (console, volumes are the console's).
- `tank_alarm_settings` already has one row per `(site_id, tank)` with `capacity_volume` and thresholds.

## 3. Changes

### 3.1 Schema (Prisma migration)

Add to `tank_alarm_settings`, both nullable:

| column | type | meaning |
|---|---|---|
| `diameter_mm` | decimal/float, > 0 | inside diameter of a **horizontal cylindrical** tank |
| `length_mm` | decimal/float, > 0 | inside length (flat ends) |

Geometry is "configured" only when both are set. Keep `capacity_volume` as is; when geometry is set,
capacity can be derived (see 3.3) and should take precedence over a hand-typed `capacity_volume` for
percentage alarms, or the admin page should show the derived value for the user to copy.

### 3.2 API

- `PUT /api/v1/devices/{site_id}/tanks/{tank}` accepts `diameter_mm`, `length_mm` (validate > 0, `null` clears).
- `GET /api/v1/devices/{site_id}/tanks` returns them in each tank row.
- Admin page `/admin#alarms/<site_id>`: two inputs next to `capacity_volume`, and show the derived capacity.

### 3.3 Volume model (pure function, unit-tested)

Horizontal cylinder, flat ends, liquid height `h` from the bottom, diameter `D`, length `L` (all mm).
Fill fraction of the cross-section:

```
r = D / 2
theta = 2 * acos((r - h) / r)          // h clamped to [0, D] first
fraction(h) = (theta - sin(theta)) / (2 * pi)
capacity_l = pi * r^2 * L / 1e6         // mm^3 -> litres
volume_l(h) = fraction(h) * capacity_l
```

Derived values per tank:

```
water_volume = volume_l(water_height)
fuel_volume  = volume_l(fuel_height) - volume_l(water_height)   // net product, water excluded
ullage       = capacity_l - volume_l(fuel_height)
fill_percent = volume_l(fuel_height) / capacity_l * 100          // gross, for the % alarms
```

Rules: clamp heights to `[0, D]`; if `water_height > fuel_height` treat fuel as 0 net and flag nothing
(just compute); if a height is missing or not a number, return `null` for every derived field.

Reference values for tests (D = 2040 mm; fractions are independent of L):

| h (mm) | fraction |
|---|---|
| 0 | 0.000000 |
| 87.1 | 0.014784 |
| 300 | 0.091397 |
| 1020 (= D/2) | 0.500000 |
| 1564 | 0.822666 |
| 1800 | 0.933966 |
| 2040 (= D) | 1.000000 |
| 2500 (over) | 1.000000 |

With D = 2040 and L = 6120 (illustrative, gives 20003.3 L): fuel_height 1564 and water_height 87.1 →
`water_volume 295.7`, `fuel_volume 16160.3`, `ullage 3547.3`. Round outputs to 1 decimal.

### 3.4 Storage: compute at ingest, store beside the payload

Add a nullable JSON column `computed` to `logs` (Prisma `Json?`). On `POST /api/v1/logs`, after the
payload passes validation and before the row is inserted:

1. Load geometry for `(site_id, tank)` for every tank in `payload.inventory.tanks` (one query, cached per request).
2. For tanks with geometry, evaluate section 3.3 and build the `computed` object below.
3. Insert the row with `payload` (verbatim) and `computed` (or `null` when no tank has geometry).

Do **not** modify `payload`, and do **not** write derived values into any existing key inside it.
Console-reported volumes must survive untouched. `computed` is a sibling column, never a field inside the
stored payload JSON.

Stored / returned shape (identical in `GET /api/v1/logs`, `GET /api/v1/logs/latest` and the `POST` reply):

```json
{
  "id": 123, "site_id": "station-2", "collected_at": "...", "received_at": "...",
  "payload": { "...verbatim..." },
  "alerts": [ ... ],
  "computed": {
    "geometry_version": "2026-09-18T07:12:00Z",
    "inventory": [
      {"tank": 3, "source": "geometry", "diameter_mm": 2040, "length_mm": 6120,
       "capacity_volume": 20003.3, "fuel_volume": 16160.3, "water_volume": 295.7,
       "ullage": 3547.3, "fill_percent": 82.3}
    ]
  }
}
```

- One entry per tank that has geometry; tanks without geometry are omitted. `computed` is `null` when none has it.
- `source` is always `"geometry"` for now (leaves room for a strapping-table source later).
- `diameter_mm`, `length_mm` and `geometry_version` (the `updated_at` of the tank settings row used) are
  stored with the result so a reader can tell which geometry produced it.
- Reads return the column as stored. No math on the read path.
- Applies to both `function` values. For `"i201"` logs the dashboard can show console volume and computed
  volume side by side; the console numbers stay in `payload` and are never replaced, merged or rounded.

### 3.4.1 Recompute when geometry changes

Because results are stored, editing `diameter_mm` / `length_mm` must refresh history:

- `PUT /api/v1/devices/{site_id}/tanks/{tank}` with changed geometry enqueues (or runs inline if the row
  count is small) a recompute of `logs.computed` for that `site_id`, batched by `id`, only touching the
  entry for that tank. Response includes `{"recompute": {"rows": N}}` or a job id.
- Also expose it explicitly: `POST /api/v1/devices/{site_id}/tanks/{tank}/recompute` (admin only) and a
  CLI script `bun run recompute --site station-2 --tank 3` for backfilling logs that predate this feature.
- Recompute reads `payload` only; it never writes to `payload`.

### 3.5 Alarms

Percentage thresholds (`low_fuel_percent`, `high_water_percent`) currently need `ullage` or
`capacity_volume`. Change the evaluator to prefer the stored `computed` values when present:
`fill_percent` for low fuel, `computed.water_volume / capacity_volume` for high water. Height and
temperature thresholds are unchanged. `alerts` keep their current behaviour (evaluated against current
thresholds at read time); only their inputs change.

### 3.6 Docs

Update the API docs (the Thai `05-api.md` equivalent in fuel-api, and `/docs` OpenAPI) with the two new
tank fields and the `computed` key.

## 4. Tests to add

- Unit: the fraction table above, clamping, `water_height > fuel_height`, missing heights → nulls.
- Unit: capacity from D and L (20003.3 L for 2040 × 6120).
- Ingest: `PUT .../tanks/3` with geometry, then `POST /api/v1/logs` for tank 3 → the stored row has
  `computed.inventory[0]` with the numbers above and `GET /api/v1/logs/latest?site_id=station-2` returns
  the same object without recomputing (assert the read path does not call the volume function, e.g. spy).
- Ingest: a log for a tank without geometry is stored with `computed: null`.
- Recompute: store a log, then change `length_mm`; the row's `computed` is refreshed and
  `geometry_version` changes; `payload` is identical before and after.
- Backfill: the CLI recomputes rows whose `computed` is `null` for a site that now has geometry.
- API (no-overwrite): store an `"i201"` log whose console volumes are `fuel_volume 15126`, `ullage 4874`,
  `water_volume 892`; after setting geometry, `payload.inventory.tanks[0]` still returns exactly those
  numbers while `computed.inventory[0]` returns the geometry-based ones. Re-read the row from the
  database to prove nothing was rewritten.
- API: `PUT` rejects `diameter_mm <= 0`, accepts `null` to clear.
- Alarm: a probe log (`function: "pokcenser"`, volumes 0) with geometry and `low_fuel_percent: 90`
  produces a low-fuel alert at 82.3 %.

## 5. Out of scope

- `tc_volume` (temperature-compensated volume): no coefficient available, leave as in payload.
- Dished/elliptical tank ends and tilt: flat-end cylinder only. If needed later, add an
  `end_volume_l` correction or a strapping table with a `"table"` source.
- No change on the Pi.

## 6. Acceptance

- [ ] Migration adds the two nullable tank columns and the nullable `logs.computed` column; existing rows untouched.
- [ ] Volumes are computed once at ingest; reads return the stored column unchanged.
- [ ] Changing geometry recomputes that tank's history; backfill CLI exists for older rows.
- [ ] `computed` appears only for tanks with geometry and never mutates `payload`.
- [ ] Console-reported volumes in `payload` are byte-for-byte unchanged after geometry is set (no-overwrite test).
- [ ] Reference fractions match to 1e-5.
- [ ] Percentage alarms work for a probe log once geometry is set.
- [ ] Existing tests still green.
