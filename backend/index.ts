/**
 * Dev server for fuel-level readings.
 *
 *   bun run dev                 # http://localhost:3000, data in ./data/fuel.sqlite
 *   PORT=8080 API_KEY=secret bun run dev
 *
 * Point the Python poller at it:
 *   python3 main.py --api-url http://<this-host>:3000/readings [--api-key secret]
 */

import { openStore } from "./src/db";
import { createServer } from "./src/routes";

const PORT = Number(Bun.env.PORT ?? 3000);
const HOSTNAME = Bun.env.HOST ?? "0.0.0.0";
const DB_PATH = Bun.env.DB_PATH ?? "./data/fuel.sqlite";
const API_KEY = Bun.env.API_KEY || undefined;

if (DB_PATH !== ":memory:") {
  await Bun.write(`${DB_PATH.replace(/[^/]+$/, "")}.keep`, "");
}

const store = openStore(DB_PATH);
const server = createServer({ port: PORT, hostname: HOSTNAME, store, apiKey: API_KEY });

console.log(`fuel-level API listening on ${server.url}`);
console.log(`  db:   ${DB_PATH}`);
console.log(`  auth: ${API_KEY ? "Bearer token required" : "none (set API_KEY to enable)"}`);
console.log(`  POST ${server.url}readings   GET ${server.url}readings?site_id=&limit=   GET ${server.url}readings/latest`);

const shutdown = () => {
  server.stop();
  store.close();
  process.exit(0);
};
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
