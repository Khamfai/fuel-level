# 05 REST API

Base URL ระหว่างพัฒนา: `http://100.82.56.28:3000`

ทุก response เป็น JSON ถ้าตั้ง `API_KEY` ไว้ ทุก route ยกเว้น `/health` ต้องส่ง header
`Authorization: Bearer <key>` ไม่งั้นได้ `401 {"error":"unauthorized"}`

## POST /readings

Pi เรียก endpoint นี้ทุกรอบ body คือ JSON ที่ `main.py` สร้าง

| สถานะ | ความหมาย |
|---|---|
| `201` | เก็บแล้ว ตอบกลับ row ที่เก็บพร้อม `id` และ `received_at` |
| `400` | body ไม่ใช่ JSON |
| `422` | JSON ผิดรูปแบบ ตอบ `{"error":"invalid reading","errors":[...]}` |
| `401` | ไม่มี/ผิด API key |

กฎการตรวจสอบ (`backend/src/schema.ts`):

- `site_id` ต้องเป็น string ไม่ว่าง
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

- `collected_at` เวลาของ Pi (UTC) ตอนอ่าน
- `timestamp` ในแต่ละ section คือนาฬิกาของ gauge ไม่มี timezone อาจเป็น `null`
- section ที่ไม่ได้ขอใน `--reports` หรืออ่านไม่ผ่าน จะไม่มีใน body

ทดสอบด้วย curl:

```bash
curl -X POST http://100.82.56.28:3000/readings \
  -H 'content-type: application/json' \
  -d '{"site_id":"test","collected_at":"2026-09-15T00:00:00Z","inventory":{"function":"i201","timestamp":null,"tanks":[{"tank":1,"volume":500}]}}'
```

## GET /readings

รายการล่าสุดก่อน

| query | default | ความหมาย |
|---|---|---|
| `site_id` | ทุกสถานี | กรองเฉพาะสถานี |
| `limit` | 50 | จำนวนสูงสุด (ไม่เกิน 1000) |

```bash
curl 'http://100.82.56.28:3000/readings?site_id=station-1&limit=10'
```

รูปแบบแต่ละแถว:

```json
{
  "id": 1,
  "site_id": "station-1",
  "collected_at": "2026-09-15T04:30:00+00:00",
  "received_at": "2026-09-15T04:30:00.123Z",
  "payload": { "...body ที่ POST มาทั้งก้อน..." }
}
```

## GET /readings/latest

ค่าล่าสุดของแต่ละสถานี (หนึ่งแถวต่อ `site_id`) เหมาะกับหน้า dashboard

```bash
curl http://100.82.56.28:3000/readings/latest
curl 'http://100.82.56.28:3000/readings/latest?site_id=station-1'
```

## GET /health

ตอบ `{"ok":true}` เสมอ ไม่ต้องใช้ API key ใช้เช็คว่า server เปิดอยู่

## การเก็บข้อมูล

SQLite ตาราง `readings` เก็บ `payload` เป็น JSON ทั้งก้อน มี index ที่ `(site_id, collected_at)`
ไฟล์อยู่ที่ `backend/data/fuel.sqlite` ดูข้อมูลตรงได้ด้วย:

```bash
sqlite3 backend/data/fuel.sqlite 'select id, site_id, collected_at from readings order by id desc limit 5'
```
