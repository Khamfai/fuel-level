# 02 ติดตั้ง Bun dev server บน Mac

server นี้เป็นตัวรับข้อมูลชั่วคราวระหว่างพัฒนา เก็บข้อมูลลง SQLite ในเครื่อง

## ติดตั้งครั้งแรก

```bash
brew install oven-sh/bun/bun     # ถ้ายังไม่มี bun
cd ~/Desktop/fuel-level/backend
bun install
```

## รัน

```bash
bun run dev
```

จะเห็น:

```
fuel-level API listening on http://0.0.0.0:3000/
  db:   ./data/fuel.sqlite
  auth: none (set API_KEY to enable)
```

`bun run dev` ใช้ `--hot` แก้โค้ดแล้ว reload เอง ไฟล์ SQLite อยู่ที่ `backend/data/fuel.sqlite`
(อยู่ใน .gitignore) ปิด server ด้วย Ctrl+C

ต้องเปิด server ค้างไว้ตลอดเวลาที่ Pi ส่งข้อมูล ถ้าปิดอยู่ Pi จะ log `cannot reach`
แล้วลองใหม่รอบถัดไป ข้อมูลรอบที่ส่งไม่ได้จะหายไป

## ตั้งค่า

ใส่ใน `backend/.env` (Bun โหลดให้เอง) หรือส่งเป็น env ตอนรัน

| ตัวแปร | ค่า default | ความหมาย |
|--------|-------------|----------|
| `PORT` | `3000` | port ที่เปิดรับ |
| `HOST` | `0.0.0.0` | รับจากทุก interface (จำเป็นเพื่อให้ Pi เข้าถึงได้) |
| `DB_PATH` | `./data/fuel.sqlite` | ไฟล์ SQLite |
| `API_KEY` | ไม่ตั้ง | ถ้าตั้ง ทุก route ยกเว้น `/health` ต้องส่ง `Authorization: Bearer <key>` |

ตัวอย่างเปิด auth:

```bash
API_KEY=secret bun run dev
```

แล้วฝั่ง Pi ต้องใส่ `TLS_API_KEY=secret` ใน `/etc/default/fuel-level`

## ตรวจว่า Pi ส่งมาถึงไหม

```bash
curl http://localhost:3000/health
curl http://localhost:3000/readings/latest | python3 -m json.tool
```

log ของ server จะพิมพ์ทุก request เช่น `POST /readings -> 201 (1.7ms)`

## คำสั่งอื่น

```bash
bun test              # รัน tests
bun run typecheck     # ตรวจ TypeScript
bun start             # รันแบบไม่ hot reload
```

## เช็ค Tailscale

Pi เรียก Mac ผ่าน IP Tailscale `100.82.56.28` ดู IP ปัจจุบันด้วย:

```bash
tailscale ip -4
```

ถ้า IP เปลี่ยน ต้องแก้ `TLS_API_URL` ใน `/etc/default/fuel-level` บน Pi
