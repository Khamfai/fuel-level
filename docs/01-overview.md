# 01 ภาพรวมระบบ

## ส่วนประกอบ

```
 ถังน้ำมัน                Raspberry Pi                          Server (Dokploy)
┌──────────────┐  RS-232  ┌─────────────────────┐   HTTP POST   ┌──────────────────────┐
│ Veeder-Root  │ ───────► │ main.py (Python)    │ ────────────► │ fuel-api (Bun/Elysia)│
│ TLS-350      │ ◄─────── │ systemd: fuel-level │  JSON ทุก 60s  │ MariaDB/MySQL        │
└──────────────┘          └─────────────────────┘               └──────────────────────┘
                           /dev/ttyUSB0                          https://atg.moomou.com
```

หรือแบบไม่มี console: ต่อโพรบเข้า Pi โดยตรง

```
 ถังน้ำมัน                      Raspberry Pi
┌──────────────┐  RS-485  ┌──────────┐  USB  ┌─────────────────────┐   HTTP POST
│ โพรบ Pokcenser│ ───────► │ USB-RS485│ ────► │ main.py             │ ────────────► server เดิม
│ PWL-M200     │ ◄─────── │ converter│       │ TLS_SOURCE=pokcenser│
└──────────────┘          └──────────┘       └─────────────────────┘
   ▲ 24 VDC
```

1. **Gauge (TLS-350)** ตอบคำสั่งผ่าน serial เป็นข้อความ ASCII ตามโปรโตคอลของ Veeder-Root
   หรือ **โพรบ PWL-M200** ตอบคำถาม 2 ไบต์ด้วยข้อความ `ระดับน้ำมัน:ระดับน้ำ:อุณหภูมิ` ที่ 4800 baud
   (ดู [07-probe-direct.md](07-probe-direct.md)) เลือกแบบใดแบบหนึ่งต่อ Pi ด้วย `TLS_SOURCE`
2. **Raspberry Pi** รัน `main.py` เป็น service ตอน boot ส่งคำสั่งไปถาม gauge ทุก 60 วินาที
   แปลงคำตอบเป็น JSON แล้ว POST ไปที่ server
3. **Server** fuel-api (repo แยก) รับ JSON ตรวจสอบรูปแบบ เก็บลง MariaDB/MySQL
   มี GET endpoint ให้ dashboard ดึงข้อมูลไปแสดงผล ดู [02-server.md](02-server.md)

ทุกรอบ Pi ส่ง heartbeat ก่อนอ่าน gauge เพื่อให้ server รู้ว่า device ยังทำงานแม้ gauge จะไม่ตอบ

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
python3 -m unittest discover -s tests      # ฝั่ง Python (79 tests)
python3 mock_server.py                     # server จำลอง แล้วรัน main.py --api-url http://127.0.0.1:8000
```
