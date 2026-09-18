# 02 Server (fuel-api)

Pi ส่งข้อมูลไปที่ `https://atg.moomou.com` ซึ่งเป็น fuel-api ที่ deploy บน Dokploy
โค้ดฝั่ง server อยู่คนละ repo (`fuel-api`: Bun + Elysia + Prisma บน MariaDB/MySQL) ไม่ได้อยู่ในโปรเจกต์นี้
รายละเอียด endpoint และรูปแบบ JSON ดู [05-api.md](05-api.md)

## ตรวจว่า server เปิดอยู่

```bash
curl https://atg.moomou.com/health                       # ต้องได้ {"success":true,"data":{"ok":true}}
curl https://atg.moomou.com/api/v1/logs/latest -H 'x-api-key: <key>' | python3 -m json.tool
```

เอกสาร interactive อยู่ที่ `https://atg.moomou.com/docs`

## ชี้ Pi ไปที่ server อื่น

ค่า default ของ `TLS_API_URL` คือ `https://atg.moomou.com` ถ้าจะใช้ server ทดสอบอื่น
แก้ใน `/etc/default/fuel-level` แล้ว `sudo systemctl restart fuel-level`

```bash
TLS_API_URL=https://staging.example.com     # base URL ไม่ต้องมี path
TLS_API_KEY=<key ของ server นั้น>
```

ค่าเก่าที่ลงท้ายด้วย `/readings`, `/v1/logs` หรือ `/api/v1/logs` ยังใช้ได้ โปรแกรมตัด path ทิ้งให้

## ทดสอบโดยไม่ต้องมี server

`mock_server.py` ในโปรเจกต์นี้เป็น server จำลองแบบไม่ต้องติดตั้งอะไร รับทุก request แล้วพิมพ์ออกจอ
ใช้ดู payload ที่ Pi จะส่งจริง

```bash
python3 mock_server.py                            # เปิดที่ http://127.0.0.1:8000
python3 main.py --api-url http://127.0.0.1:8000   # ส่งไปที่ mock หนึ่งรอบ
```

ตอบด้วย envelope แบบเดียวกับ server จริง (`201` สำหรับ log, `200` สำหรับ heartbeat, `201` สำหรับลงทะเบียน device)
