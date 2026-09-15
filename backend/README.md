# backend

Dev API that receives tank readings from the Python poller (`../main.py`) and stores them in SQLite.

```bash
bun install
bun run dev            # http://localhost:3000 with hot reload, db in ./data/fuel.sqlite
bun test               # unit + route tests
bun run typecheck
```

Environment (Bun loads `.env` automatically): `PORT` (3000), `HOST` (0.0.0.0), `DB_PATH` (./data/fuel.sqlite), `API_KEY` (unset = no auth; when set, every route except /health needs `Authorization: Bearer <key>`).

| Route | Purpose |
|-------|---------|
| `POST /readings` | Accepts the poller payload (see ../README.md). 201 with the stored row, 400 bad JSON, 422 validation errors. |
| `GET /readings?site_id=&limit=` | Newest first, default 50, max 1000. |
| `GET /readings/latest?site_id=` | Most recent reading per site. |
| `GET /health` | `{"ok": true}` |

Layout: `src/schema.ts` validation, `src/db.ts` SQLite store, `src/routes.ts` handlers, `index.ts` entry point.

Point the poller at it from the Pi (replace the IP with this machine's):

```bash
python3 main.py --api-url http://192.168.1.10:3000/readings --interval 60
```
