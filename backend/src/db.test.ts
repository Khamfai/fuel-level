import { describe, expect, test } from "bun:test";
import { openStore } from "./db";

const reading = (site_id: string, collected_at: string) => ({
  site_id,
  collected_at,
  inventory: { function: "i201", timestamp: null, tanks: [{ tank: 1, volume: 500 }] },
});

describe("ReadingStore", () => {
  test("insert returns the stored row with an id", () => {
    const store = openStore(":memory:");
    const row = store.insert(reading("a", "2026-09-15T01:00:00Z"));
    expect(row.id).toBe(1);
    expect(row.payload.inventory?.tanks[0]).toEqual({ tank: 1, volume: 500 });
    expect(row.received_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  test("list returns newest first and filters by site", () => {
    const store = openStore(":memory:");
    store.insert(reading("a", "2026-09-15T01:00:00Z"));
    store.insert(reading("b", "2026-09-15T02:00:00Z"));
    store.insert(reading("a", "2026-09-15T03:00:00Z"));

    expect(store.list({}).map((r) => r.collected_at)).toEqual([
      "2026-09-15T03:00:00Z", "2026-09-15T02:00:00Z", "2026-09-15T01:00:00Z",
    ]);
    expect(store.list({ siteId: "a" })).toHaveLength(2);
    expect(store.list({ limit: 1 })).toHaveLength(1);
  });

  test("latest returns one row per site", () => {
    const store = openStore(":memory:");
    store.insert(reading("a", "2026-09-15T01:00:00Z"));
    store.insert(reading("a", "2026-09-15T03:00:00Z"));
    store.insert(reading("b", "2026-09-15T02:00:00Z"));

    const latest = store.latest();
    expect(latest.map((r) => [r.site_id, r.collected_at])).toEqual([
      ["a", "2026-09-15T03:00:00Z"],
      ["b", "2026-09-15T02:00:00Z"],
    ]);
    expect(store.latest("b")).toHaveLength(1);
  });
});
