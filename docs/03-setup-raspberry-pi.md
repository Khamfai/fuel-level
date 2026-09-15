# 03 ติดตั้งบน Raspberry Pi

ทดสอบกับ Raspberry Pi 3, user `backup`, โปรเจกต์อยู่ที่ `/home/backup/fuel-level`

## ความต้องการ

- Python 3.9 ขึ้นไป (`python3 --version`) Raspberry Pi OS Bullseye/Bookworm ใช้ได้
- สาย USB-to-RS232 ต่อจาก Pi ไปที่ port serial ของ gauge จะเห็นเป็น `/dev/ttyUSB0`
- Pi ต่อ Tailscale เดียวกับ Mac (`tailscale status`)

## 1. copy โปรเจกต์ไปที่ Pi

ต้อง copy **ทั้งโฟลเดอร์** ไม่ใช่แค่ `main.py` เพราะโค้ดอยู่ในโฟลเดอร์ `tls/` ด้วย

```bash
# รันบน Mac
scp -r ~/Desktop/fuel-level backup@<pi-ip>:~/
```

โครงสร้างบน Pi ต้องมี `main.py`, `tls/`, `deploy/` อยู่ในโฟลเดอร์เดียวกัน

## 2. ทดลองรันด้วยมือก่อน

```bash
ssh backup@<pi-ip>
cd ~/fuel-level
sudo apt install -y python3-serial      # หรือ pip3 install pyserial
sudo usermod -aG dialout $USER          # สิทธิ์อ่าน serial port แล้ว logout/login ใหม่

python3 main.py --dry-run               # อ่าน gauge แล้วพิมพ์ JSON ไม่ส่ง
python3 main.py                         # อ่านแล้วส่งไป Mac ครั้งเดียว
python3 main.py -v                      # แสดง raw bytes ที่ gauge ตอบ ใช้ตอน debug
```

ถ้า `--dry-run` แสดง JSON ที่มีค่า `volume` `height` ถูกต้อง แปลว่าสายและ baud rate ใช้ได้

## 3. ตั้งให้รันตอน boot

```bash
cd ~/fuel-level
sudo bash deploy/install.sh
```

สคริปต์จะ:

1. เพิ่ม user เข้ากลุ่ม `dialout`
2. ติดตั้ง pyserial ถ้ายังไม่มี
3. สร้าง `/etc/systemd/system/fuel-level.service` โดยแทนที่ user และ path ให้ตรงเครื่อง
4. สร้าง `/etc/default/fuel-level` จากตัวอย่าง (ถ้ายังไม่มี)
5. เปิด auto-start และเริ่ม service ทันที

## 4. ตั้งค่า

แก้ที่ `/etc/default/fuel-level` (ทุกบรรทัดใส่หรือไม่ใส่ก็ได้)

```bash
TLS_PORT=/dev/ttyUSB0
TLS_BAUD=9600
TLS_API_URL=http://100.82.56.28:3000/readings
TLS_API_KEY=
TLS_SITE_ID=station-1
POLL_INTERVAL=60
```

แก้แล้วสั่ง `sudo systemctl restart fuel-level`

`TLS_SITE_ID` ใช้แยกข้อมูลถ้ามีหลายสถานี ควรตั้งชื่อให้ไม่ซ้ำกันในแต่ละ Pi

## คำสั่งดูแล service

```bash
sudo systemctl status fuel-level     # รันอยู่ไหม
journalctl -u fuel-level -f          # ดู log สด (Ctrl+C ออก)
journalctl -u fuel-level --since "1 hour ago"
sudo systemctl restart fuel-level    # หลังแก้โค้ดหรือ config
sudo systemctl stop fuel-level       # หยุดชั่วคราว
sudo systemctl disable fuel-level    # ปิด auto-start
```

## อัปเดตโค้ด

```bash
# บน Mac
scp -r ~/Desktop/fuel-level/main.py ~/Desktop/fuel-level/tls backup@<pi-ip>:~/fuel-level/
# บน Pi
sudo systemctl restart fuel-level
```

## พฤติกรรมของ service

- เริ่มหลัง network พร้อม (`network-online.target`)
- อ่าน gauge ทุก `POLL_INTERVAL` วินาที
- ถ้ารายงานใดอ่านไม่ได้ (เช่น 205 parse ไม่ผ่าน) จะข้ามรายงานนั้นแล้วส่งที่เหลือ
- ถ้า server ติดต่อไม่ได้จะ log error แล้วรอรอบถัดไป ไม่หยุดทำงาน
- ถ้าโปรแกรม crash systemd จะเริ่มใหม่ใน 10 วินาที
