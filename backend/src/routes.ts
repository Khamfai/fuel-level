/** HTTP API: POST /readings from the gauge poller, GET endpoints for dashboards. */

import type { BunRequest, Server } from "bun";
import type { ReadingStore } from "./db";
import { validateReading } from "./schema";

export type ServerOptions = {
  port: number;
  store: ReadingStore;
  hostname?: string;
  apiKey?: string;
  quiet?: boolean;
};

const json = (data: unknown, status = 200): Response =>
  Response.json(data, { status });

export function createServer(opts: ServerOptions): Server<undefined> {
  const { store, apiKey, quiet = false } = opts;

  const guard =
    (handler: (req: BunRequest) => Response | Promise<Response>) =>
    async (req: BunRequest): Promise<Response> => {
      const started = performance.now();
      let res: Response;
      try {
        res = isAuthorized(req, apiKey) ? await handler(req) : json({ error: "unauthorized" }, 401);
      } catch (err) {
        console.error(err);
        res = json({ error: "internal error" }, 500);
      }
      if (!quiet) logRequest(req, res.status, performance.now() - started);
      return res;
    };

  return Bun.serve({
    port: opts.port,
    hostname: opts.hostname,
    development: true,
    routes: {
      "/health": { GET: () => json({ ok: true }) },
      "/readings": {
        POST: guard(async (req) => {
          let body: unknown;
          try {
            body = await req.json();
          } catch {
            return json({ error: "body is not valid JSON" }, 400);
          }
          const result = validateReading(body);
          if (!result.ok) return json({ error: "invalid reading", errors: result.errors }, 422);
          return json(store.insert(result.value), 201);
        }),
        GET: guard((req) => {
          const url = new URL(req.url);
          const siteId = url.searchParams.get("site_id") ?? undefined;
          const limit = Number(url.searchParams.get("limit") ?? "") || undefined;
          return json(store.list({ siteId, limit }));
        }),
      },
      "/readings/latest": {
        GET: guard((req) => {
          const siteId = new URL(req.url).searchParams.get("site_id") ?? undefined;
          return json(store.latest(siteId));
        }),
      },
    },
    fetch: (req) => {
      if (!quiet) logRequest(req, 404, 0);
      return json({ error: `no route for ${req.method} ${new URL(req.url).pathname}` }, 404);
    },
  });
}

function isAuthorized(req: Request, apiKey: string | undefined): boolean {
  if (!apiKey) return true;
  return req.headers.get("authorization") === `Bearer ${apiKey}`;
}

function logRequest(req: Request, status: number, ms: number): void {
  const { pathname, search } = new URL(req.url);
  console.log(`${new Date().toISOString()} ${req.method} ${pathname}${search} -> ${status} (${ms.toFixed(1)}ms)`);
}
