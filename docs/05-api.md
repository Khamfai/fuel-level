# 05 REST API

Base URL บน production: `https://atg.moomou.com`
(ตอนพัฒนาบนเครื่องเดียวกันใช้ `http://localhost:3000`) เอกสารแบบ interactive อยู่ที่ `{base}/docs`
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
| `POST /api/v1/devices` | body `{"site_id","name","lat","lng"}` → `201` device, `409` ถ้า site มีอยู่แล้ว, `422` ถ้าข้อมูลผิด (เช่น lat > 90) |
| `GET /api/v1/devices?page=&limit=&status=` | รายการเรียงตาม `site_id` กรอง `status=online` หรือ `offline` ได้ |
| `GET /api/v1/devices/{site_id}` | device เดียว `404` ถ้าไม่มี |
| `PUT /api/v1/devices/{site_id}` | แก้ `name`, `lat`, `lng` บางฟิลด์ |
| `DELETE /api/v1/devices/{site_id}` | ลบ `409` ถ้ายังมี log อยู่ |
| `POST /api/v1/devices/{site_id}/heartbeat` | บอกว่า device ยังทำงาน ไม่ต้องมี body ตอบ device พร้อม `online: true` |

ฟิลด์ของ device:

```json
{
  "id": 1, "site_id": "station-1", "name": "Station 1", "lat": 13.7563, "lng": 100.5018,
  "created_at": "...", "updated_at": "...",
  "last_heartbeat_at": "2026-09-16T05:00:00.000Z",
  "last_log_at": "2026-09-16T04:59:30.000Z",
  "last_seen_at": "2026-09-16T05:00:00.000Z",
  "online": true
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

## GET /api/v1/logs/latest

ค่าล่าสุดของแต่ละสถานี (หนึ่งแถวต่อ `site_id`) เหมาะกับหน้า dashboard ไม่มี `metadata`

```bash
curl https://atg.moomou.com/api/v1/logs/latest -H 'x-api-key: <key>'
curl 'https://atg.moomou.com/api/v1/logs/latest?site_id=station-1' -H 'x-api-key: <key>'
```

## GET /health

ตอบ `{"success":true,"data":{"ok":true}}` เสมอ ไม่ต้องใช้ API key ใช้เช็คว่า server เปิดอยู่

## การเก็บข้อมูล

MariaDB/MySQL ตาราง `devices` (หนึ่งแถวต่อ site) และ `logs` (`payload` เป็น JSON ทั้งก้อน, FK `logs.site_id → devices.site_id`)
มี index ที่ `(site_id, collected_at)` schema อยู่ใน repo `fuel-api` ที่ `prisma/schema.prisma`
