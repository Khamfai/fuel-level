import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { openStore } from "./db";
import { createServer } from "./routes";

const payload = {
  site_id: "station-7",
  collected_at: "2026-09-15T06:30:04+00:00",
  inventory: { function: "i201", timestamp: "2026-09-15T12:30:00", tanks: [{ tank: 1, volume: 1000 }] },
};

const readJson = <T = any>(res: Response) => res.json() as Promise<T>;

const post = (url: string, body: unknown, headers: Record<string, string> = {}) =>
  fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });

describe("open server", () => {
  const server = createServer({ port: 0, store: openStore(":memory:"), quiet: true });
  const base = server.url.origin;
  afterAll(() => server.stop(true));

  test("GET /health", async () => {
    const res = await fetch(`${base}/health`);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
  });

  test("POST /readings stores and returns the id", async () => {
    const res = await post(`${base}/readings`, payload);
    expect(res.status).toBe(201);
    const body = await readJson(res);
    expect(body.id).toBe(1);
    expect(body.site_id).toBe("station-7");
  });

  test("POST /readings with bad JSON -> 400", async () => {
    const res = await post(`${base}/readings`, "{not json");
    expect(res.status).toBe(400);
  });

  test("POST /readings with invalid payload -> 422 and errors", async () => {
    const res = await post(`${base}/readings`, { site_id: "x" });
    expect(res.status).toBe(422);
    expect((await readJson(res)).errors.length).toBeGreaterThan(0);
  });

  test("GET /readings lists what was posted", async () => {
    const res = await fetch(`${base}/readings?site_id=station-7&limit=5`);
    expect(res.status).toBe(200);
    const rows = await readJson(res);
    expect(rows).toHaveLength(1);
    expect(rows[0].payload.inventory.tanks[0].volume).toBe(1000);
  });

  test("GET /readings/latest", async () => {
    const res = await fetch(`${base}/readings/latest`);
    expect(res.status).toBe(200);
    expect((await readJson(res))[0].site_id).toBe("station-7");
  });

  test("unknown route -> 404 JSON", async () => {
    const res = await fetch(`${base}/nope`);
    expect(res.status).toBe(404);
    expect((await readJson(res)).error).toBeDefined();
  });
});

describe("server with API key", () => {
  const server = createServer({ port: 0, store: openStore(":memory:"), apiKey: "secret", quiet: true });
  const base = server.url.origin;
  afterAll(() => server.stop(true));

  test("rejects a missing or wrong token", async () => {
    expect((await post(`${base}/readings`, payload)).status).toBe(401);
    expect((await post(`${base}/readings`, payload, { authorization: "Bearer wrong" })).status).toBe(401);
    expect((await fetch(`${base}/readings`)).status).toBe(401);
  });

  test("accepts the right token", async () => {
    const res = await post(`${base}/readings`, payload, { authorization: "Bearer secret" });
    expect(res.status).toBe(201);
  });

  test("health stays open", async () => {
    expect((await fetch(`${base}/health`)).status).toBe(200);
  });
});
