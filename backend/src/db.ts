/** SQLite persistence for readings (bun:sqlite). Rows keep the full JSON payload. */

import { Database } from "bun:sqlite";
import type { Reading } from "./schema";

export type StoredReading = {
  id: number;
  site_id: string;
  collected_at: string;
  received_at: string;
  payload: Reading;
};

type Row = Omit<StoredReading, "payload"> & { payload: string };

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 1000;

const SCHEMA = `
  CREATE TABLE IF NOT EXISTS readings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id      TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    payload      TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS readings_site_time ON readings (site_id, collected_at DESC);
`;

export class ReadingStore {
  constructor(private readonly db: Database) {
    db.exec("PRAGMA journal_mode = WAL");
    db.exec(SCHEMA);
  }

  insert(reading: Reading): StoredReading {
    const received_at = new Date().toISOString();
    const row = this.db
      .query<Row, [string, string, string, string]>(
        `INSERT INTO readings (site_id, collected_at, received_at, payload)
         VALUES (?, ?, ?, ?) RETURNING *`,
      )
      .get(reading.site_id, reading.collected_at, received_at, JSON.stringify(reading));
    if (!row) throw new Error("insert returned no row");
    return hydrate(row);
  }

  list({ siteId, limit = DEFAULT_LIMIT }: { siteId?: string; limit?: number }): StoredReading[] {
    const capped = Math.min(Math.max(1, Math.floor(limit)), MAX_LIMIT);
    const rows = siteId
      ? this.db
          .query<Row, [string, number]>(
            `SELECT * FROM readings WHERE site_id = ? ORDER BY collected_at DESC, id DESC LIMIT ?`,
          )
          .all(siteId, capped)
      : this.db
          .query<Row, [number]>(`SELECT * FROM readings ORDER BY collected_at DESC, id DESC LIMIT ?`)
          .all(capped);
    return rows.map(hydrate);
  }

  /** Most recent reading for each site (or just the given site). */
  latest(siteId?: string): StoredReading[] {
    const sql = `
      SELECT r.* FROM readings r
      JOIN (SELECT site_id, MAX(collected_at) AS collected_at FROM readings
            ${siteId ? "WHERE site_id = ?" : ""} GROUP BY site_id) m
        ON m.site_id = r.site_id AND m.collected_at = r.collected_at
      ORDER BY r.site_id`;
    const rows = siteId
      ? this.db.query<Row, [string]>(sql).all(siteId)
      : this.db.query<Row, []>(sql).all();
    return rows.map(hydrate);
  }

  close(): void {
    this.db.close();
  }
}

const hydrate = (row: Row): StoredReading => ({ ...row, payload: JSON.parse(row.payload) as Reading });

export function openStore(path: string): ReadingStore {
  return new ReadingStore(new Database(path, { create: true }));
}
