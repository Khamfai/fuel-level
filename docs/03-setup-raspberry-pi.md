# 03 ติดตั้งบน Raspberry Pi

ทดสอบกับ Raspberry Pi 3, user `backup`, โปรเจกต์อยู่ที่ `/home/backup/fuel-level`

## เลือกแบบการต่อก่อน

โค้ดชุดเดียวใช้ได้ 2 แบบ เลือกแบบใดแบบหนึ่งต่อ Pi หนึ่งเครื่อง

| แบบ | ต่ออย่างไร | ค่าใน config |
|-----|-----------|--------------|
| **A. console TLS-350** (แบบเดิม) | สาย USB-to-RS232 จาก Pi ไป port serial ของ console | ไม่ต้องใส่ `TLS_SOURCE` |
| **B. โพรบ PWL-M200 โดยตรง** | สาย USB-to-RS485 จาก Pi ไปขั้ว A/B ของโพรบ ไม่ผ่าน console | `TLS_SOURCE=pokcenser` และ `TLS_PROBE_ADDRS=<เลขถัง>` |

รายละเอียดการเดินสายและโปรโตคอลของแบบ B อยู่ที่ [07-probe-direct.md](07-probe-direct.md)
ขั้นตอนติดตั้งด้านล่างเหมือนกันทั้งสองแบบ ต่างกันแค่ config ในข้อ 4

## ความต้องการ

- Python 3.9 ขึ้นไป (`python3 --version`) Raspberry Pi OS Bullseye/Bookworm ใช้ได้
- แบบ A: สาย USB-to-RS232 ต่อจาก Pi ไปที่ port serial ของ console จะเห็นเป็น `/dev/ttyUSB0`
- แบบ B: สาย USB-to-RS485 (เช่น FT232RL + 75176) ต่อขั้ว A/B และ GND ไปที่โพรบ และโพรบต้องมีไฟ 24 VDC
- อะแดปเตอร์ Pi ต้องจ่ายได้ 5 V 3 A ถ้า `dmesg | grep -i undervoltage` มีข้อความ ตัวแปลง USB จะหลุดเป็นระยะ
- Pi ต่อ Tailscale เดียวกับ Mac (`tailscale status`)

## 1. copy โปรเจกต์ไปที่ Pi

ต้อง copy **ทั้งโฟลเดอร์** ไม่ใช่แค่ `main.py` เพราะโค้ดอยู่ในโฟลเดอร์ `tls/` และ `pokcenser/` ด้วย

```bash
# รันบน Mac
scp -r ~/Desktop/fuel-level backup@<pi-ip>:~/
```

โครงสร้างบน Pi ต้องมี `main.py`, `probe_scan.py`, `tls/`, `pokcenser/`, `deploy/` อยู่ในโฟลเดอร์เดียวกัน

## 2. ทดลองรันด้วยมือก่อน

```bash
ssh backup@<pi-ip>
cd ~/fuel-level
sudo apt install -y python3-serial      # หรือ pip3 install pyserial
sudo usermod -aG dialout $USER          # สิทธิ์อ่าน serial port แล้ว logout/login ใหม่

# แบบ A: console TLS-350
python3 main.py --dry-run               # อ่าน gauge แล้วพิมพ์ JSON ไม่ส่ง
python3 main.py                         # อ่านแล้วส่งไป server ครั้งเดียว
python3 main.py -v                      # แสดง raw bytes ที่ gauge ตอบ ใช้ตอน debug

# แบบ B: โพรบโดยตรง
python3 probe_scan.py --find            # ไล่ถามถัง 1 ถึง 8 ว่าโพรบตอบที่เลขไหน
python3 main.py --source pokcenser --probe-addrs 3 --dry-run
```

ถ้า `--dry-run` แสดง JSON ที่มีค่า `fuel_height` `water_height` `temperature` ถูกต้อง แปลว่าสายและ baud rate ใช้ได้
(แบบ B จะได้ `fuel_volume` เป็น 0 เพราะโพรบไม่มีตารางเทียบถัง)

ถ้าเคยติดตั้ง service ไว้แล้ว ให้ `sudo systemctl stop fuel-level` ก่อนทดลองด้วยมือ ไม่งั้นจะแย่ง serial port กัน

## 3. ตั้งให้รันตอน boot

```bash
cd ~/fuel-level
sudo bash deploy/install.sh
```
### ทดสอบระดับ raw (แบบ A)
```python
python3 -c "
from tls.transport import TlsGauge
with TlsGauge('/dev/ttyUSB0') as g:
    print('i201', g.query('i201', '00'))
    print('i205', g.query('i205', '00'))
    print('I205', g.query('I205', '00'))
"
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
TLS_SOURCE=pokcenser                    # แบบ B เท่านั้น แบบ A ไม่ต้องใส่บรรทัดนี้
TLS_PROBE_ADDRS=3                       # แบบ B: เลขถังตามหน้าจอ console คั่นด้วย , ถ้ามีหลายถัง
TLS_PORT=/dev/ttyUSB0
#TLS_BAUD=9600                          # ปล่อยว่างไว้ โค้ดเลือกให้เอง (9600 สำหรับ A, 4800 สำหรับ B)
TLS_API_URL=https://atg.moomou.com            # base URL ไม่ต้องมี path
TLS_DEVICE_NAME=Station 1               # ใส่ทั้ง 3 ค่านี้เพื่อลงทะเบียน device ตอนเริ่ม
TLS_LAT=13.7563
TLS_LNG=100.5018
TLS_API_KEY=
TLS_SITE_ID=station-1
POLL_INTERVAL=60
```

แก้แล้วสั่ง `sudo systemctl restart fuel-level` แล้วดู `journalctl -u fuel-level -n 5` ต้องเห็น
`posted 1 report(s) ... -> HTTP 201`

`TLS_SITE_ID` ใช้แยกข้อมูลถ้ามีหลายสถานี ควรตั้งชื่อให้ไม่ซ้ำกันในแต่ละ Pi

### เปลี่ยนเครื่องที่ติดตั้งแบบ A อยู่แล้วให้เป็นแบบ B

```bash
sudo cp /etc/default/fuel-level /etc/default/fuel-level.bak-tls
sudo sed -i -e 's/^TLS_BAUD=.*/#TLS_BAUD=/' -e '$a TLS_SOURCE=pokcenser\nTLS_PROBE_ADDRS=3' /etc/default/fuel-level
sudo systemctl restart fuel-level && sleep 15 && journalctl -u fuel-level -n 5 --no-pager
```

บรรทัด `TLS_BAUD=9600` ต้องถูกคอมเมนต์ทิ้งจริง ไม่งั้นจะไปทับ 4800 ของโพรบ

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
cd ~/Desktop/fuel-level
scp -r main.py probe_scan.py tls pokcenser backup@<pi-ip>:~/fuel-level/
# บน Pi
sudo systemctl restart fuel-level
```

## พฤติกรรมของ service

- เริ่มหลัง network พร้อม (`network-online.target`)
- อ่าน gauge หรือโพรบทุก `POLL_INTERVAL` วินาที
- แบบ A: ถ้ารายงานใดอ่านไม่ได้ (เช่น 205 parse ไม่ผ่าน) จะข้ามรายงานนั้นแล้วส่งที่เหลือ
- แบบ B: ถ้าถังใดไม่ตอบจะข้ามถังนั้น ส่งเฉพาะถังที่อ่านได้ ล้มเหลวเมื่อทุกถังไม่ตอบ
- ถ้า server ติดต่อไม่ได้จะ log error แล้วรอรอบถัดไป ไม่หยุดทำงาน
- ถ้าโปรแกรม crash systemd จะเริ่มใหม่ใน 10 วินาที