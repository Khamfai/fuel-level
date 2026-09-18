# 05 REST API

Base URL บน production: `https://atg.moomou.com` (fuel-api บน Dokploy ดู [02-server.md](02-server.md))
ทดสอบโดยไม่แตะ server จริงใช้ `python3 mock_server.py` แล้ว `--api-url http://127.0.0.1:8000`
เอกสารแบบ interactive อยู่ที่ `{base}/docs`
และ OpenAPI ที่ `{base}/docs/json`

ทุก response เป็น **envelope** เดียวกัน

```json
{ "success": true,  "data": { ... } }                                   // สำเร็จ
{ "success": true,  "data": [ ... ], "metadata": { "total": 1, "limit": 50, "page": 1 } }   // รายการแบบแบ่งหน้า
{ "success": false, "data": null, "error": { "message": "...", "details": ["..."] } }        // ล้มเหลว
```

ถ้า server ตั้ง `API_KEY` ไว้ ทุก route ยกเว้น `GET /`, `GET /health` และ `/docs` ต้องส่ง header
`Authorization: Bearer <key>` (หรือ `x-api-key: <key>`) ไม่งั้นได้ `401`

รหัสตอบกลับ: `400` body ไม่ใช่ JSON, `401` ไม่มี/ผิด key, `404` ไม่พบ, `409` ข้อมูลชนกัน,
`422` ข้อมูลไม่ผ่านการตรวจหรือยังไม่มี device ของ site นั้น, `500` ผิดพลาดใน server

## ลำดับที่ Pi เรียก

1. ตอนเริ่ม (ถ้าตั้ง `TLS_DEVICE_NAME`/`TLS_LAT`/`TLS_LNG`): `POST /api/v1/devices` ลงทะเบียน device ของ site
2. ทุกรอบ: `POST /api/v1/devices/{site_id}/heartbeat` แล้วค่อยอ่าน gauge
3. ทุกรอบ: `POST /api/v1/logs` ส่งรายงาน

## Devices

หนึ่ง site มีหนึ่ง device (`site_id` ไม่ซ้ำ) server รับ log เฉพาะ site ที่มี device แล้ว

| Route | ความหมาย |
|---|---|
| `POST /api/v1/devices` | body `{"site_id","name","lat","lng"}` → `201` device (ถ้า site นั้นเคยถูกลบ จะกู้คืนด้วยข้อมูลใหม่), `409` ถ้า site มี device ที่ยังใช้งานอยู่, `422` ถ้าข้อมูลผิด (เช่น lat > 90) |
| `GET /api/v1/devices?page=&limit=&status=&include_deleted=` | รายการเรียงตาม `site_id` กรอง `status=online` หรือ `offline` ได้ device ที่ถูกลบ (soft delete) จะแสดงเมื่อ `include_deleted=true` เท่านั้น |
| `GET /api/v1/devices/{site_id}` | device เดียว `404` ถ้าไม่มี |
| `PUT /api/v1/devices/{site_id}` | แก้ `name`, `lat`, `lng`, `is_deleted` บางฟิลด์ (`is_deleted: false` = กู้คืน device ที่ลบไป) |
| `DELETE /api/v1/devices/{site_id}` | soft delete: แถวและ log ยังอยู่ แต่หายจากรายการและ **ปฏิเสธ log/heartbeat** ของ site นั้น (`422 unknown site_id` / `404`) `404` ถ้าไม่มีหรือลบไปแล้ว |
| `POST /api/v1/devices/{site_id}/heartbeat` | บอกว่า device ยังทำงาน ไม่ต้องมี body ตอบ device พร้อม `online: true` |

ฟิลด์ของ device:

```json
{
  "id": 1, "site_id": "station-1", "name": "Station 1", "lat": 13.7563, "lng": 100.5018,
  "created_at": "...", "updated_at": "...",
  "last_heartbeat_at": "2026-09-16T05:00:00.000Z",
  "last_log_at": "2026-09-16T04:59:30.000Z",
  "last_seen_at": "2026-09-16T05:00:00.000Z",
  "online": true,
  "is_deleted": false
}
```

`online` เป็นจริงเมื่อ `last_seen_at` (ค่าล่าสุดระหว่าง heartbeat กับ log ที่รับสำเร็จ ใช้นาฬิกา server)
อายุไม่เกิน `DEVICE_OFFLINE_AFTER_SEC` ของ server (ค่าเริ่มต้น 180 วินาที = 3 รอบของ `--interval 60`)

ลงทะเบียนด้วย curl:

```bash
curl -X POST https://atg.moomou.com/api/v1/devices \
  -H 'content-type: application/json' -H 'x-api-key: <key>' \
  -d '{"site_id":"station-1","name":"Station 1","lat":13.7563,"lng":100.5018}'
```

## Tank alarm thresholds (ตั้งจากหน้าเว็บ ไม่เกี่ยวกับ Pi)

ผู้ดูแลตั้งเกณฑ์เตือนต่อถังได้ที่ `/admin#configs/<site_id>` (หน้า Configs) หรือผ่าน API; server เป็นคนตัดสินแล้วส่งผลกลับเป็น `alerts` ในทุก log

| Route | ความหมาย |
|---|---|
| `GET /api/v1/devices/{site_id}/tanks` | `data: { defaults, tanks: [...] }` ถังที่ตั้งค่าไว้ของ site และค่าเริ่มต้นที่ถังอื่นใช้ |
| `PUT /api/v1/devices/{site_id}/tanks/{tank}` | สร้าง/แก้แถวของถัง: `label`, `capacity_volume` (L), `low_fuel_percent`, `low_fuel_volume` (L), `high_water_height` (mm), `high_water_percent`, `high_temperature` (°C) และ `segments` (ถังกายภาพ ดูด้านล่าง; `diameter_mm` + `length_mm` เป็นทางลัดของถังตรงใบเดียว) ทุกฟิลด์ optional ส่ง `null` เพื่อปิดเกณฑ์ `404` ถ้าไม่มี device ถ้า geometry เปลี่ยน server คำนวณ `computed` ของ log ทั้งประวัติใหม่และตอบ `recompute.rows` |
| `PUT /api/v1/devices/{site_id}/tanks/{tank}/calibration` | แทนที่จุดสอบเทียบทั้งชุด `[{"height_mm", "volume_l", "note"?}]` (array ว่าง = ลบทั้งหมด) แล้วคำนวณประวัติใหม่ |
| `POST /api/v1/devices/{site_id}/tanks/{tank}/recompute` | คำนวณ `computed` ใหม่ให้ log ทุกแถวของ site ที่มีถังนี้ (backfill log ที่เก็บก่อนตั้ง geometry) |
| `DELETE /api/v1/devices/{site_id}/tanks/{tank}` | ลบแถว กลับไปใช้ค่าเริ่มต้น (`TANK_LOW_FUEL_PERCENT` 20, `TANK_HIGH_WATER_PERCENT` 2 ของ server) |

ถังที่มีแถวของตัวเองจะถูกตัดสินจากแถวนั้นเท่านั้น ถังที่ไม่มีแถวใช้ค่าเริ่มต้นสองข้อ (% น้ำมันต่ำ, % น้ำสูง)
เกณฑ์ % ต้องมี `ullage` จาก gauge หรือ `capacity_volume` ในแถว alarm ของ gauge เอง (`status.tanks[].alarms`) เป็นคนละอย่างและยังแสดงแยกกัน

## ปริมาตรจากความสูง (Pokcenser probe)

probe ส่งแค่ `fuel_height`, `water_height` (mm จากจุดศูนย์ของ probe) และ `temperature` ส่วนปริมาตรเป็น `0` เมื่อผู้ดูแลตั้ง geometry ของถัง
server จะคำนวณลิตร **ครั้งเดียวตอน POST** แล้วเก็บในคอลัมน์ `computed` ข้าง ๆ `payload` ทุกแถวของ `GET /api/v1/logs` และ `/logs/latest` มี `computed`
(หรือ `null` ถ้าไม่มีถังไหนมี geometry)

ถัง logical หนึ่งหมายเลข (ตามที่ probe รายงาน) อาจเป็นถังกายภาพ 1 ใบหรือหลายใบที่ท่อเชื่อมกัน (ระดับเท่ากัน ปริมาตรบวกกัน) แต่ละใบใน `segments` มี
`diameter_front_mm`, `diameter_back_mm` (ไม่ใส่ = เท่าด้านหน้า ถ้าต่างกันถือเป็นถังเรียวและ integrate ตามแนวยาว), `length_mm` (เฉพาะส่วนกระบอก),
`bottom_offset_mm` (ก้นถังใบนี้สูงกว่าจุดศูนย์ของ probe เท่าไร ค่าเริ่มต้น 0) และ `head_type` (`flat`, `ellipsoidal`, `torispherical`)
จุดสอบเทียบ (`…/calibration`) คือคู่ (ความสูง, ลิตรจริง) จากไม้จุ่มหรือใบส่งน้ำมัน server จะปรับเส้นโค้งจาก geometry ให้ผ่านจุดเหล่านี้ (`source` เป็น `calibrated`)

```json
"computed": {
  "geometry_version": "2026-09-18T07:12:00.000Z",
  "inventory": [
    {"tank": 3, "source": "geometry", "segments": 1, "calibration_points": 0,
     "capacity_volume": 20003.3, "fuel_volume": 16160.3, "water_volume": 295.7, "ullage": 3547.3, "fill_percent": 82.3}
  ]
}
```

`fuel_volume` เป็นน้ำมันสุทธิ (คอลัมน์ของเหลวลบน้ำที่อยู่ข้างล่าง) `fill_percent` คือของเหลวทั้งหมดต่อความจุ
`payload` ไม่ถูกแก้เลย: log จาก console (`i201`) ยังมีปริมาตรของ console อยู่ครบ และ `computed` วางคู่กัน
เกณฑ์เตือนแบบ % และลิตรใช้ `computed` เมื่อมี Pi ไม่ต้องแก้อะไร

## POST /api/v1/logs

Pi เรียก endpoint นี้ทุกรอบ body คือ JSON ที่ `main.py` สร้าง

| สถานะ | ความหมาย |
|---|---|
| `201` | เก็บแล้ว `data` คือ row ที่เก็บพร้อม `id` และ `received_at` |
| `400` | body ไม่ใช่ JSON |
| `422` | JSON ผิดรูปแบบ (`error.message` = `invalid log` พร้อม `details`) หรือยังไม่มี device ของ `site_id` (`unknown site_id`) |
| `401` | ไม่มี/ผิด API key |

กฎการตรวจสอบ:

- `site_id` ต้องเป็น string ไม่ว่าง และต้องมี device ลงทะเบียนแล้ว
- `collected_at` ต้องเป็นวันที่ ISO-8601
- ต้องมีอย่างน้อยหนึ่งใน `inventory`, `status`, `delivery`
- แต่ละ section ต้องมี `function` (string) และ `tanks` (array)

ตัวอย่าง body:

```json
{
  "site_id": "station-1",
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
  }
}
```

- `collected_at` เวลาของ Pi (UTC) ตอนอ่าน
- `timestamp` ในแต่ละ section คือนาฬิกาของ gauge ไม่มี timezone อาจเป็น `null`
- section ที่ไม่ได้ขอใน `--reports` หรืออ่านไม่ผ่าน จะไม่มีใน body
- server เก็บ `payload` เป็นคอลัมน์ JSON ลำดับ key ตอนอ่านกลับอาจต่างจากที่ส่ง

### body จากโหมดโพรบ (`TLS_SOURCE=pokcenser`)

รูปแบบเดียวกัน แต่มีเฉพาะ section `inventory` และค่าบางฟิลด์ต่างจาก console

```json
{
  "site_id": "station-2",
  "collected_at": "2026-09-18T04:49:02+00:00",
  "inventory": {
    "function": "pokcenser",
    "timestamp": null,
    "tanks": [
      {"tank": 3, "fuel_volume": 0.0, "tc_volume": 0.0, "ullage": 0.0,
       "fuel_height": 1564.0, "water_height": 87.1, "temperature": 26.9, "water_volume": 0.0}
    ]
  }
}
```

| ฟิลด์ | โหมดโพรบ |
|-------|----------|
| `function` | `"pokcenser"` ใช้แยกได้ว่า log นี้มาจากโพรบไม่ใช่ console |
| `timestamp` | `null` เสมอ โพรบไม่มีนาฬิกา ใช้ `collected_at` แทน |
| `tank` | เลขถังตามหน้าจอ console (ค่าใน `TLS_PROBE_ADDRS`) |
| `fuel_height`, `water_height` | mm จากโพรบ |
| `temperature` | °C จากโพรบ |
| `fuel_volume`, `tc_volume`, `ullage`, `water_volume` | `0` เสมอ โพรบไม่มีตารางเทียบถัง |
| `status`, `delivery` | ไม่มี โพรบไม่มี alarm และประวัติการเติม |

ผลต่อ tank alarm thresholds: เกณฑ์แบบเปอร์เซ็นต์ (`low_fuel_percent`, `high_water_percent`) คำนวณไม่ได้
เพราะ `ullage` และ `fuel_volume` เป็น 0 ให้ตั้งเกณฑ์แบบความสูงหรืออุณหภูมิแทน (`high_water_height`, `high_temperature`)
หรือใส่ `capacity_volume` ของถังในแถว alarm ถ้า server รองรับการคำนวณจากความสูง

ทดสอบด้วย curl:

```bash
curl -X POST https://atg.moomou.com/api/v1/logs \
  -H 'content-type: application/json' -H 'x-api-key: <key>' \
  -d '{"site_id":"station-1","collected_at":"2026-09-15T00:00:00Z","inventory":{"function":"i201","timestamp":null,"tanks":[{"tank":1,"fuel_volume":500}]}}'
```

## GET /api/v1/logs

รายการล่าสุดก่อน แบ่งหน้า

| query | default | ความหมาย |
|---|---|---|
| `site_id` | ทุกสถานี | กรองเฉพาะสถานี |
| `page` | 1 | หน้าที่ต้องการ (≥ 1) |
| `limit` | 50 | จำนวนต่อหน้า (1–1000) |

`metadata.total` คือจำนวนทั้งหมดที่ตรง `site_id` ไม่สนใจการแบ่งหน้า ค่า `page`/`limit` ที่ไม่ใช่จำนวนเต็มได้ `422`

```bash
curl 'https://atg.moomou.com/api/v1/logs?site_id=station-1&limit=10' -H 'x-api-key: <key>'
```

รูปแบบแต่ละแถวใน `data`:

```json
{
  "id": 1,
  "site_id": "station-1",
  "collected_at": "2026-09-15T04:30:00+00:00",
  "received_at": "2026-09-15T04:30:00.123Z",
  "payload": { "...body ที่ POST มาทั้งก้อน..." }
}
```

แต่ละแถวมี `alerts` เพิ่ม: เกณฑ์ที่ inventory ของ log นั้นข้าม (ตัดสินด้วยการตั้งค่าปัจจุบัน) เช่น
`[{"tank": 2, "metric": "low_fuel_percent", "level": "warn", "value": 15, "threshold": 20, "message": "Tank 2 fuel is 15%, below 20%"}]`
ว่าง `[]` เมื่อไม่มีอะไรข้าม และ `tank_labels` = `[{"tank": 1, "label": "Diesel"}]` ชื่อถังจากหน้า Configs (เฉพาะถังที่ตั้งชื่อไว้)

## GET /api/v1/logs/latest

ค่าล่าสุดของแต่ละสถานี (หนึ่งแถวต่อ `site_id`) เหมาะกับหน้า dashboard ไม่มี `metadata` มี `alerts` เหมือน `GET /api/v1/logs`

```bash
curl https://atg.moomou.com/api/v1/logs/latest -H 'x-api-key: <key>'
curl 'https://atg.moomou.com/api/v1/logs/latest?site_id=station-1' -H 'x-api-key: <key>'
```

## GET /health

ตอบ `{"success":true,"data":{"ok":true}}` เสมอ ไม่ต้องใช้ API key ใช้เช็คว่า server เปิดอยู่

## การเก็บข้อมูล

MariaDB/MySQL ตาราง `devices` (หนึ่งแถวต่อ site), `logs` (`payload` เป็น JSON ทั้งก้อน, FK `logs.site_id → devices.site_id`) และ `tank_alarm_settings` (เกณฑ์ต่อถัง)
มี index ที่ `(site_id, collected_at)` schema อยู่ใน repo `fuel-api` ที่ `prisma/schema.prisma`
