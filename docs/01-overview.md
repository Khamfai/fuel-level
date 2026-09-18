# 01 ภาพรวมระบบ

## ส่วนประกอบ

```
 ถังน้ำมัน                Raspberry Pi                          Mac (dev server)
┌──────────────┐  RS-232  ┌─────────────────────┐   HTTP POST   ┌──────────────────────┐
│ Veeder-Root  │ ───────► │ main.py (Python)    │ ────────────► │ backend/ (Bun)       │
│ TLS-350      │ ◄─────── │ systemd: fuel-level │  JSON ทุก 60s  │ SQLite: data/fuel.db │
└──────────────┘          └─────────────────────┘               └──────────────────────┘
                           /dev/ttyUSB0                          https://atg.moomou.com
```

1. **Gauge (TLS-350)** ตอบคำสั่งผ่าน serial เป็นข้อความ ASCII ตามโปรโตคอลของ Veeder-Root
   (หรือต่อโพรบ Pokcenser PWL-M200 เข้า Pi โดยตรงผ่าน RS-485 ดู [07-probe-direct.md](07-probe-direct.md))
2. **Raspberry Pi** รัน `main.py` เป็น service ตอน boot ส่งคำสั่งไปถาม gauge ทุก 60 วินาที
   แปลงคำตอบเป็น JSON แล้ว POST ไปที่ server
3. **Mac** รัน Bun server รับ JSON ตรวจสอบรูปแบบ แล้วเก็บลง SQLite
   มี GET endpoint ให้ดึงข้อมูลไปแสดงผล

API ตัวจริงรันบน Coolify ที่ `https://atg.moomou.com` (ระหว่างพัฒนาอาจชี้ไป Mac ผ่าน Tailscale แทน) ทุกรอบ Pi ส่ง heartbeat ก่อนอ่าน gauge เพื่อให้ server รู้ว่า device ยังทำงานแม้ gauge จะไม่ตอบ

## โครงสร้างไฟล์

```
fuel-level/
├── main.py              CLI ฝั่ง Pi: อ่าน gauge สร้าง JSON ส่ง API
├── tls/
│   ├── protocol.py      สร้างคำสั่ง ตรวจ checksum แปลงคำตอบ 201 / 205 / 20C
│   ├── transport.py     คุยกับ serial port (TlsGauge) หา port อัตโนมัติ
│   └── api.py           ApiClient (POST JSON) และ build_payload
├── pokcenser/
│   ├── protocol.py      โปรโตคอล ASCII ของ console CM1 (4800 baud, CRC-8) ที่ดักได้จากสายจริง
│   └── probe.py         PokProbe ถามโพรบตามเลขถังของ console แล้วคืน InventoryReport แบบเดียวกับ TLS
├── probe_scan.py        เครื่องมือหน้างาน: หา address ของโพรบ อ่านค่าดิบ
├── tests/               unit tests ฝั่ง Python  →  python3 -m unittest discover -s tests
├── deploy/
│   ├── fuel-level.service   systemd unit
│   ├── fuel-level.env.example  ตัวอย่างค่า config
│   └── install.sh           สคริปต์ติดตั้งบน Pi
├── mock_server.py       server จำลองแบบไม่ต้องลงอะไร ใช้ดู payload
├── backend/             Bun dev server
│   ├── index.ts         จุดเริ่ม อ่าน env เปิด DB
│   └── src/
│       ├── schema.ts    ตรวจสอบรูปแบบ JSON ที่รับเข้ามา
│       ├── db.ts        SQLite store (bun:sqlite)
│       └── routes.ts    HTTP handlers, auth, logging
└── docs/                เอกสารชุดนี้
```

## รายงานที่อ่านได้

| ชื่อใน `--reports` | รหัสคำสั่ง | ความหมาย | ส่งเป็น default |
|---|---|---|---|
| `inventory` | 201 | ตอนนี้ในถังมีน้ำมัน / น้ำ / อุณหภูมิเท่าไหร่ | ใช่ |
| `status` | 205 | ถังมี alarm อะไรอยู่บ้าง | ใช่ |
| `delivery` | 20C | การเติมน้ำมันครั้งล่าสุด เติมเมื่อไหร่ เท่าไหร่ | ไม่ |

รายละเอียดแต่ละ field ดูที่ [04-gauge-protocol.md](04-gauge-protocol.md)

## ทดสอบโดยไม่ต้องมี gauge

```bash
python3 -m unittest discover -s tests      # ฝั่ง Python (18 tests)
cd backend && bun test                     # ฝั่ง server (19 tests)
```
