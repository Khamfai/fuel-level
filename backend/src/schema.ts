/** Shape of the JSON the Python client (fuel-level/main.py) POSTs to /readings. */

export type ReportSection = {
  function: string;
  timestamp: string | null;
  tanks: unknown[];
};

export type Reading = {
  site_id: string;
  collected_at: string;
  inventory?: ReportSection;
  status?: ReportSection;
  delivery?: ReportSection;
};

export const SECTION_KEYS = ["inventory", "status", "delivery"] as const;
type SectionKey = (typeof SECTION_KEYS)[number];

export type ValidationResult =
  | { ok: true; value: Reading }
  | { ok: false; errors: string[] };

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function validateReading(input: unknown): ValidationResult {
  if (!isRecord(input)) return { ok: false, errors: ["body must be a JSON object"] };

  const errors: string[] = [];

  if (typeof input.site_id !== "string" || input.site_id.trim() === "") {
    errors.push("site_id must be a non-empty string");
  }
  if (typeof input.collected_at !== "string" || Number.isNaN(Date.parse(input.collected_at))) {
    errors.push("collected_at must be an ISO-8601 date string");
  }

  const present = SECTION_KEYS.filter((k) => input[k] !== undefined);
  if (present.length === 0) {
    errors.push(`at least one of ${SECTION_KEYS.join(", ")} is required`);
  }
  errors.push(...present.flatMap((k) => sectionErrors(k, input[k])));

  if (errors.length > 0) return { ok: false, errors };

  const sections = Object.fromEntries(present.map((k) => [k, input[k] as ReportSection]));
  return {
    ok: true,
    value: {
      site_id: input.site_id as string,
      collected_at: input.collected_at as string,
      ...(sections as Partial<Record<SectionKey, ReportSection>>),
    },
  };
}

function sectionErrors(key: SectionKey, value: unknown): string[] {
  if (!isRecord(value)) return [`${key} must be an object`];
  const errors: string[] = [];
  if (typeof value.function !== "string") errors.push(`${key}.function must be a string`);
  if (!Array.isArray(value.tanks)) errors.push(`${key}.tanks must be an array`);
  return errors;
}
