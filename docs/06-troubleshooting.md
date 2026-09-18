# 06 แก้ปัญหา

ดู log บน Pi ด้วย `journalctl -u fuel-level -f` หรือรัน `python3 main.py -v` ด้วยมือ

## ฝั่ง Pi

### `ModuleNotFoundError: No module named 'tls'` หรือ `'pokcenser'`

copy มาแค่ `main.py` ไม่มีโฟลเดอร์ `tls/` หรือ `pokcenser/` ให้ copy ทั้งโปรเจกต์ (`scp -r`) แล้วเช็ค `ls tls/ pokcenser/`

### `ModuleNotFoundError: No module named 'serial'`

```bash
sudo apt install -y python3-serial
```

### `No USB serial adapter found`

Pi ไม่เห็นสาย USB-to-serial

```bash
ls /dev/ttyUSB* /dev/ttyACM*     # ต้องมีอย่างน้อยหนึ่งตัว
dmesg | tail                      # ดูว่า kernel เห็นสายตอนเสียบไหม
```

ถ้าใช้ UART บนขา GPIO แทน ให้ตั้ง `TLS_PORT=/dev/serial0`

### `Permission denied: '/dev/ttyUSB0'`

user ไม่อยู่ในกลุ่ม `dialout`

```bash
sudo usermod -aG dialout $USER
```

แล้ว logout เข้าใหม่ (service ที่ติดตั้งผ่าน `install.sh` ทำให้แล้ว แต่ต้อง restart service)

### `no ETX within 10s ... (0 bytes received)`

gauge ไม่ตอบเลย ตรวจตามลำดับ:

1. สายต่อถูก port ของ gauge ไหม (TLS-350 มี port RS-232 หลายช่อง บางช่องปิดไว้)
2. baud rate ตรงกับที่ตั้งใน gauge ไหม ลอง `--baud 2400` / `4800` / `19200`
3. สาย null-modem หรือ straight ถูกแบบไหม ลองสลับ
4. gauge ตั้ง security code ไว้หรือไม่ ถ้าใช่ต้องส่งรหัสนำหน้าคำสั่ง (ยังไม่รองรับ แจ้งผู้พัฒนา)

### `no ETX within 10s ... (N bytes received)` โดย N > 0

gauge ตอบมาบางส่วน มักเป็น baud rate ผิดหรือสายมี noise รัน `-v` ดู raw bytes

### `checksum mismatch`

ข้อมูลเสียหายระหว่างทาง หรือ gauge คำนวณ checksum ต่างจากเอกสาร
ถ้าเกิดทุกครั้ง ให้ใส่ `--no-verify-checksum` ชั่วคราวและส่ง raw bytes จาก `-v` ให้ผู้พัฒนา

### `truncated response ...` หรือ `no ETX within 10s for i20500` เฉพาะรายงาน 205

gauge ตอบ 205 ไม่สม่ำเสมอเมื่อถูกถามติดกันเร็วเกินไป โปรแกรมเว้นช่วงและ retry ให้แล้ว
ถ้ายังเกิดทุกรอบ ส่งบรรทัด `raw=` จาก `journalctl -u fuel-level` ให้ผู้พัฒนา หรือตัด `status`
ออกจาก `--reports` ชั่วคราว

### `gauge rejected the command`

gauge ตอบ `9999` แปลว่าไม่รู้จักคำสั่ง รุ่น/firmware อาจไม่รองรับ function นั้น
ตัดออกจาก `--reports` ได้

## โหมดโพรบ (`TLS_SOURCE=pokcenser`)

ทดสอบด้วยมือทุกครั้งให้หยุด service ก่อน: `sudo systemctl stop fuel-level` ไม่งั้นสองโปรแกรมจะแย่ง `/dev/ttyUSB0`
และได้ error `device reports readiness to read but returned no data (... multiple access on port?)`

### `no reply within 2.0s (0 bytes received)` ทุกถัง

โพรบเงียบสนิท ไล่ตามลำดับ (เรียงจากที่พบบ่อย)

1. service ยังรันอยู่และแย่ง port `systemctl is-active fuel-level` ต้องได้ `inactive` ตอนทดสอบด้วยมือ
2. เลขถังผิด รัน `python3 probe_scan.py --find` จะไล่ถามถัง 1 ถึง 8 ให้
3. ไม่มีกราวด์ร่วม GND ของ converter ต้องต่อกับขั้วลบของไฟ 24 V ที่จ่ายให้โพรบ (สายดำ) แม้จะจ่ายไฟจาก console ก็ตาม
4. สาย A/B สลับ ลองสลับสายขาวกับน้ำเงินที่ converter
5. โพรบไม่มีไฟ วัดระหว่างสายแดงกับดำต้องได้ 24 ถึง 26 V
6. baud ไม่ใช่ 4800 ถ้ามีคนตั้ง `TLS_BAUD=9600` ค้างไว้ใน `/etc/default/fuel-level` จะไปทับค่าของโหมดนี้ ให้ลบหรือคอมเมนต์ทิ้ง

### `no reply within 2.0s (N bytes received: ...)` โดย N > 0

มีอะไรวิ่งบนสายแต่ไม่ใช่คำตอบที่ถูกต้อง

- เห็นแค่ `e2 42` (2 ไบต์) คือเสียงสะท้อนคำถามของเราเอง โพรบไม่ตอบ ดูรายการข้างบน
- เห็นไบต์แปลก ๆ จำนวนมาก เช่น `18 18 fe 18 06 98 ...` มักเป็น baud ผิด ตรวจว่า `TLS_BAUD` ไม่ได้ตั้งค่าอื่นทับ 4800

### `crc mismatch`

สัญญาณเสียหายระหว่างทาง มักเกิดจากไม่มีกราวด์ร่วม สายยาวไม่มี shield หรือ console ยังพ่วงอยู่บนสายเดียวกันจนคำตอบชนกัน

### `--find` เห็นถังที่ไม่มีจริง หรือค่าถังหนึ่งซ้ำกับอีกถัง

console ยังต่ออยู่บนสาย A/B เดียวกันและกำลังถามโพรบเองทุกวินาที คำตอบของโพรบไม่มีเลขถังกำกับ
Pi จึงหยิบคำตอบที่โพรบตอบ console มาเป็นของตัวเองได้ ให้ถอดสายขาว/น้ำเงินออกจาก console เหลือแค่สายไฟ

### `Undervoltage detected!` ใน `dmesg` และ USB หลุดเป็นระยะ

อะแดปเตอร์ของ Pi จ่ายไฟไม่พอ อาการคือ `/dev/ttyUSB0` หายไปกลางคัน หรือ error `device disconnected`
เปลี่ยนเป็นอะแดปเตอร์ 5 V 3 A ของแท้ และเลี่ยงเสียบอุปกรณ์ USB อื่นพร้อมกัน

```bash
dmesg | grep -iE "undervoltage|ftdi|disconnect" | tail
```

### `--source pokcenser only supports inventory`

ใส่ `status` หรือ `delivery` ใน `--reports` ไว้ โพรบไม่มีข้อมูลสองอย่างนี้ ลบออกหรือปล่อยให้ใช้ค่า default

### `cannot reach https://atg.moomou.com/api/v1/logs`

Pi ออกอินเทอร์เน็ตไม่ได้ หรือ server ล่ม

```bash
ping -c 3 8.8.8.8                           # เน็ตของ Pi
curl https://atg.moomou.com/health          # ต้องได้ {"success":true,"data":{"ok":true}}
```

ถ้า ping ได้แต่ health ไม่ตอบ เป็นฝั่ง server (Dokploy) ไม่ใช่ Pi ข้อมูลรอบที่ส่งไม่ได้จะหายไป
โปรแกรมไม่หยุดทำงาน จะลองใหม่รอบถัดไป

### `HTTP 401`

server ตั้ง `API_KEY` แต่ Pi ไม่ได้ส่ง ใส่ `TLS_API_KEY=<key เดียวกัน>` ใน `/etc/default/fuel-level`

### `HTTP 422`

server ปฏิเสธรูปแบบ JSON มักเกิดเมื่อ Python กับ backend เป็นคนละเวอร์ชัน อัปเดตทั้งสองฝั่งให้ตรงกัน

### service ไม่รันตอน boot

```bash
sudo systemctl is-enabled fuel-level     # ต้องได้ enabled
sudo systemctl status fuel-level
journalctl -u fuel-level -b              # log ตั้งแต่ boot ล่าสุด
```

ถ้าขึ้น `status=203/EXEC` path ใน unit file ไม่ตรง รัน `sudo bash deploy/install.sh` ใหม่

## เก็บ raw bytes ส่งให้ผู้พัฒนา

```bash
python3 main.py --dry-run -v 2>&1 | grep raw
```

### `HTTP 422 ... unknown site_id`

server ยังไม่มี device ของ `TLS_SITE_ID` นี้ ลงทะเบียนครั้งเดียวด้วย

```bash
python3 main.py --device-name "Station 1" --lat 13.7563 --lng 100.5018
```

หรือใส่ `TLS_DEVICE_NAME`, `TLS_LAT`, `TLS_LNG` ใน `/etc/default/fuel-level` แล้ว restart service
(ปล่อยค่าไว้ได้ ถ้ามีอยู่แล้ว server ตอบ 409 และ poller ถือว่าเรียบร้อย)

### `heartbeat failed: HTTP 404 ... device not found`

เหตุเดียวกับข้างบน heartbeat ล้มเหลวเป็นแค่ warning ไม่หยุดการส่ง log แต่หน้า dashboard จะเห็น device เป็น offline
