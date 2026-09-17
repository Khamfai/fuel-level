# 07 ต่อโพรบ PWL-M200 เข้า Pi โดยตรง (RS-485 Modbus)

ใช้เมื่อไม่มี console TLS-350 หรือ console CM1 ของ Pokcenser และต้องการให้ Raspberry Pi
อ่านโพรบ magnetostrictive รุ่น PWL-M200 / PWL-M300 ผ่านตัวแปลง USB-RS485 โดยตรง

```
 ถังน้ำมัน                                    Raspberry Pi
┌──────────────┐  RS-485 (A/B)  ┌────────────┐  USB  ┌─────────────────────┐
│ โพรบ PWL-M200 │ ─────────────► │ USB-RS485  │ ────► │ main.py             │
│ (Modbus addr 1)│               │ converter  │       │ --source modbus     │
└──────────────┘                └────────────┘       └─────────────────────┘
      ▲ 24 VDC                                          /dev/ttyUSB0
```

## การเดินสาย

สายจากโพรบมี 5 เส้น (ตามคู่มือติดตั้งของ Pokcenser)

| สี | หน้าที่ | ต่อเข้า |
|----|---------|---------|
| ขาว | RS-485 A | ขั้ว A ของ converter |
| น้ำเงิน | RS-485 B | ขั้ว B ของ converter |
| แดง | ไฟบวก | +24 ถึง 26 VDC |
| ดำ | ไฟลบ | ขั้วลบของแหล่งจ่าย **และ** GND ของ converter |
| เหลือง | shield | กราวด์ |

- converter FT232RL + 75176 สลับทิศทางส่ง/รับให้เอง ไม่ต้องตั้งค่าอะไรใน Pi
- ต่อโพรบหลายตัวบนสาย A/B เส้นเดียวกันได้ แต่ละตัวต้องมี address ไม่ซ้ำกัน
- โพรบใช้ 9600 baud, 8 data bits, ไม่มี parity, 1 stop bit ตามค่าโรงงาน

## หา address ของโพรบ

ต่อโพรบ **ทีละตัว** แล้วถามผ่าน broadcast

```bash
python3 probe_scan.py --find
# probe address: 7
```

ถ้าต้องการอ่านค่าดิบดูก่อนใช้งานจริง

```bash
python3 probe_scan.py --addrs 1,2,3
# addr   1: fuel   2276.6 mm  water  1320.9 mm  temp 18.19 C  points [18.2 0.0 0.0 0.0 0.0]
# addr   2: FAILED no reply within 2.0s (0 bytes received)
python3 probe_scan.py --addrs 1 --loop 5      # อ่านซ้ำทุก 5 วินาที กด Ctrl-C เพื่อหยุด
```

## รัน poller ในโหมด modbus

```bash
python3 main.py --source modbus --probe-addrs 1,2,3 --dry-run     # ดู JSON ไม่ส่งขึ้น server
python3 main.py --source modbus --probe-addrs 1,2,3 --interval 60
```

หรือตั้งใน `/etc/default/fuel-level` สำหรับ systemd

```
TLS_SOURCE=modbus
TLS_PROBE_ADDRS=1,2,3
```

- ลำดับใน `--probe-addrs` คือหมายเลขถัง: address ตัวแรกเป็นถัง 1, ตัวที่สองเป็นถัง 2
- โหมดนี้มีเฉพาะ report `inventory` (โพรบไม่มี alarm และประวัติการเติม) และเป็นค่า default อยู่แล้ว
- โพรบตัวไหนไม่ตอบจะถูกข้ามพร้อม log error รอบนั้นจะล้มเหลวก็ต่อเมื่อทุกตัวไม่ตอบ

## ข้อมูลที่ส่งขึ้น server

โพรบให้แค่ระดับน้ำมัน ระดับน้ำ และอุณหภูมิ ไม่มีตารางเทียบถัง ดังนั้น

| field | ที่มา |
|-------|-------|
| `fuel_height`, `water_height` | โพรบ หน่วย mm |
| `temperature` | โพรบ อุณหภูมิเฉลี่ยของน้ำมัน °C |
| `fuel_volume`, `tc_volume`, `ullage`, `water_volume` | ส่งเป็น `0` |
| `function` | `"pwl-m200"` |
| `timestamp` | `null` (โพรบไม่มีนาฬิกา) |

## โปรโตคอลโดยย่อ

จากเอกสาร "RS485 Protocol-PWL-M200 M300-Pokcenser-V2.0"

- Modbus RTU function 04 อ่าน 16 register จาก 0x0000 ได้ float 32 บิต 8 ค่า
  (น้ำมัน mm, น้ำ mm, อุณหภูมิเฉลี่ย, อุณหภูมิจุด A ถึง E)
- float เป็นแบบ IEEE_FLOAT_L คือสลับไบต์ในแต่ละ word เช่น `0E 45 B2 49` = `45 0E 49 B2` = 2276.6
- โพรบใช้เวลาประมาณ 1 วินาทีก่อนตอบ โค้ดรอ 2 วินาที
- address 0 (broadcast) อ่าน register 0x20 ได้ address ของโพรบ, function 06 เขียน register 0x20 เพื่อเปลี่ยน address

ตัวอย่างในเอกสาร (address 2) ใช้เป็น test vector ใน `tests/test_modbus_rtu.py`
