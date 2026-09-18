# เอกสารระบบ fuel-level

ระบบอ่านระดับน้ำมันในถังจากเครื่องวัด Veeder-Root TLS-350 ผ่านสาย RS-232 บน Raspberry Pi
แล้วส่งข้อมูลเป็น JSON ไปเก็บที่ server fuel-api (`https://atg.moomou.com`)

| เอกสาร | เนื้อหา |
|--------|---------|
| [01-overview.md](01-overview.md) | ภาพรวมระบบ ส่วนประกอบ และการไหลของข้อมูล |
| [02-server.md](02-server.md) | server fuel-api บน Dokploy, ชี้ Pi ไป server อื่น, mock server สำหรับทดสอบ |
| [03-setup-raspberry-pi.md](03-setup-raspberry-pi.md) | ติดตั้ง Python poller บน Pi และตั้งให้รันตอน boot |
| [04-gauge-protocol.md](04-gauge-protocol.md) | โปรโตคอลของ gauge: คำสั่ง 201 / 205 / 20C และความหมายของแต่ละ field |
| [05-api.md](05-api.md) | REST API: endpoint, รูปแบบ JSON, รหัสตอบกลับ |
| [06-troubleshooting.md](06-troubleshooting.md) | ข้อผิดพลาดที่พบบ่อยและวิธีแก้ |
| [07-probe-direct.md](07-probe-direct.md) | ต่อโพรบ PWL-M200 เข้า Pi โดยตรงผ่าน RS-485 โดยไม่ใช้ console (โปรโตคอลจริงที่ดักได้จากสาย) |
