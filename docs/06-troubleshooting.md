# 06 แก้ปัญหา

ดู log บน Pi ด้วย `journalctl -u fuel-level -f` หรือรัน `python3 main.py -v` ด้วยมือ

## ฝั่ง Pi

### `ModuleNotFoundError: No module named 'tls'`

copy มาแค่ `main.py` ไม่มีโฟลเดอร์ `tls/` ให้ copy ทั้งโปรเจกต์ (`scp -r`) แล้วเช็ค `ls tls/`

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

### `cannot reach https://fuelms-fuelapi-fbqlk8-0155fc-103-66-238-99.sslip.io/v1/logs`

Mac ไม่ได้เปิด server หรือ Tailscale ไม่เชื่อม

```bash
tailscale status                              # บน Pi ต้องเห็น Mac
curl https://fuelms-fuelapi-fbqlk8-0155fc-103-66-238-99.sslip.io/health          # ต้องได้ {"success":true,"data":{"ok":true}}
```

บน Mac ต้องรัน `bun run dev` ค้างไว้ และ IP จาก `tailscale ip -4` ต้องตรงกับ `TLS_API_URL`

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

## ฝั่ง Mac

### `bun: command not found`

```bash
brew install oven-sh/bun/bun
```

### `EADDRINUSE` port 3000 ถูกใช้อยู่

มี server เก่ารันค้าง

```bash
lsof -i :3000
kill <pid>
```

หรือรันบน port อื่น `PORT=3001 bun run dev` แล้วแก้ `TLS_API_URL` บน Pi

### Pi ส่งมาแต่ไม่เห็นใน log

`HOST` ต้องเป็น `0.0.0.0` (ค่า default) ถ้าตั้งเป็น `127.0.0.1` เครื่องอื่นจะเข้าไม่ได้
และ macOS Firewall อาจถาม อนุญาต bun ตอนเปิดครั้งแรก

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
