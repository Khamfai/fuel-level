import { describe, expect, test } from "bun:test";
import { validateReading } from "./schema";

const inventory = { function: "i201", timestamp: "2026-09-15T12:30:00", tanks: [{ tank: 1, volume: 1000 }] };
const valid = { site_id: "station-7", collected_at: "2026-09-15T06:30:04+00:00", inventory };

describe("validateReading", () => {
  test("accepts a payload with one report section", () => {
    const result = validateReading(valid);
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.site_id).toBe("station-7");
  });

  test("rejects a non-object body", () => {
    const result = validateReading("nope");
    expect(result.ok).toBe(false);
  });

  test("rejects a missing site_id", () => {
    const result = validateReading({ ...valid, site_id: "" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.join()).toContain("site_id");
  });

  test("rejects an unparseable collected_at", () => {
    const result = validateReading({ ...valid, collected_at: "yesterday" });
    expect(result.ok).toBe(false);
  });

  test("rejects a payload with no report sections", () => {
    const result = validateReading({ site_id: "s", collected_at: valid.collected_at });
    expect(result.ok).toBe(false);
  });

  test("rejects a section whose tanks is not an array", () => {
    const result = validateReading({ ...valid, status: { function: "i205", tanks: "x" } });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.join()).toContain("status.tanks");
  });
});
