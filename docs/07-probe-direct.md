# 07 ต่อโพรบ PWL-M200 เข้า Pi โดยตรง (RS-485 ไม่ใช้ console)

ใช้เมื่อต้องการให้ Raspberry Pi อ่านโพรบ magnetostrictive รุ่น PWL-M200 / PWL-M300 ของ Pokcenser
ผ่านตัวแปลง USB-RS485 โดยตรง ไม่ผ่าน console CM1

```
 ถังน้ำมัน                                    Raspberry Pi
┌──────────────┐  RS-485 (A/B)  ┌────────────┐  USB  ┌─────────────────────┐
│ โพรบ PWL-M200 │ ─────────────► │ USB-RS485  │ ────► │ main.py             │
│ (ถัง 3)       │               │ converter  │       │ --source pokcenser  │
└──────────────┘                └────────────┘       └─────────────────────┘
      ▲ 24 VDC                                          /dev/ttyUSB0
```

## ข้อควรรู้ก่อน: เอกสารผู้ผลิตไม่ตรงกับของจริง

เอกสาร "RS485 Protocol-PWL-M200 M300 V2.0" บอกว่าโพรบใช้ Modbus RTU ที่ 9600 baud
แต่โพรบที่มากับ console CM1 **ไม่ตอบ Modbus เลย** สิ่งที่ดักได้จากสายระหว่าง console กับโพรบคือ

| รายการ | ค่าจริง |
|--------|---------|
| ความเร็ว | **4800** baud, 8 data bits, ไม่มี parity, 1 stop bit |
| คำถาม | 2 ไบต์: `0xE0 + (เลขถัง − 1)` ตามด้วยตัวอักษร `B` เช่น ถัง 3 = `E2 42` |
| คำตอบ | `STX` `1564.0:87.1:26.9` `ETX` แล้วตามด้วย checksum 1 ไบต์ |
| ความหมาย | ระดับน้ำมัน mm : ระดับน้ำ mm : อุณหภูมิ °C |
| checksum | CRC-8 แบบ Dallas/Maxim (poly 0x31 กลับบิต, init 0) คำนวณตั้งแต่ STX ถึง ETX |
| เวลาตอบ | ประมาณ 0.85 วินาที |

โค้ดโหมด `pokcenser` ทำตามตารางนี้ ไม่มีโค้ด Modbus ในโปรเจกต์ เพราะโพรบไม่เคยตอบ

## การเดินสาย

สายจากโพรบมี 5 เส้น (ตามคู่มือติดตั้งของ Pokcenser)

| สี | หน้าที่ | ต่อเข้า |
|----|---------|---------|
| ขาว | RS-485 A | ขั้ว A ของ converter |
| น้ำเงิน | RS-485 B | ขั้ว B ของ converter |
| แดง | ไฟบวก | +24 ถึง 26 VDC |
| ดำ | ไฟลบ | ขั้วลบของแหล่งจ่าย **และ** GND ของ converter |
| เหลือง | shield | กราวด์ |

- ถ้ายังใช้ console จ่ายไฟให้โพรบ ให้ต่อเฉพาะสายแดง/ดำเข้า console ส่วนขาว/น้ำเงินเข้า converter อย่างเดียว
- **อย่าให้ console อยู่บนสาย A/B เดียวกับ converter** เพราะ console จะถามโพรบทุกวินาทีและคำตอบของโพรบไม่มีเลขถังกำกับ
  Pi อาจหยิบคำตอบที่โพรบตอบ console มาเป็นของตัวเอง (`--find` จะเห็นถังเงาที่ไม่มีจริง)
- ไฟเลี้ยง Pi ต้องพอ ถ้า `dmesg` ขึ้น `Undervoltage detected` ตัวแปลง USB จะหลุดเป็นระยะ ให้เปลี่ยนอะแดปเตอร์เป็น 5 V 3 A

## หาว่าโพรบตอบที่เลขถังไหน

หยุด service ก่อน เพราะมันเปิด port ค้างอยู่

```bash
sudo systemctl stop fuel-level
python3 probe_scan.py --find
# tank 3: answers  fuel 1564.0 mm  water 87.1 mm  temp 26.9 C
# use: --probe-addrs 3
python3 probe_scan.py --addrs 3 --loop 5      # อ่านซ้ำทุก 5 วินาที กด Ctrl-C เพื่อหยุด
```

## รัน poller ในโหมด pokcenser

```bash
python3 main.py --source pokcenser --probe-addrs 3 --dry-run     # ดู JSON ไม่ส่งขึ้น server
python3 main.py --source pokcenser --probe-addrs 3 --interval 60
```

สำหรับ systemd แก้ `/etc/default/fuel-level` แล้ว `sudo systemctl restart fuel-level`

```
TLS_SOURCE=pokcenser
TLS_PROBE_ADDRS=3
# ลบหรือคอมเมนต์ TLS_BAUD ทิ้ง (ค่า 9600 จะไปทับ 4800 ของโหมดนี้)
```

- `--probe-addrs` คือเลขถังตามหน้าจอ console และจะเป็นค่า `tank` ใน payload
- โหมดนี้มีเฉพาะ report `inventory` (โพรบไม่มี alarm และประวัติการเติม) และเป็นค่า default อยู่แล้ว
- ถังที่ตั้งเลขไว้แต่ไม่ตอบ (ไม่ได้ต่อหรืออ่านไม่ได้) จะยังถูกส่งขึ้น server โดยทุกค่าเป็น 0 เหมือนที่ console แสดง 0.0 สำหรับถังที่ไม่มีโพรบ พร้อม log error รอบนั้นจะล้มเหลวก็ต่อเมื่อทุกถังไม่ตอบ

## ข้อมูลที่ส่งขึ้น server

| field | ที่มา |
|-------|-------|
| `fuel_height`, `water_height` | โพรบ หน่วย mm |
| `temperature` | โพรบ °C |
| `fuel_volume`, `tc_volume`, `ullage`, `water_volume` | ส่งเป็น `0` (ตารางเทียบถังอยู่ใน console ไม่ใช่ในโพรบ) |
| `function` | `"pokcenser"` |
| `timestamp` | `null` (โพรบไม่มีนาฬิกา) |
