import { Database } from "bun:sqlite";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { drizzle } from "drizzle-orm/bun-sqlite";
import { migrate } from "drizzle-orm/bun-sqlite/migrator";

import * as schema from "./schema";

const path = process.env.DATABASE_PATH ?? "./data/prins.db";
if (path !== ":memory:") mkdirSync(dirname(path), { recursive: true });

const sqlite = new Database(path, { create: true });
sqlite.run("PRAGMA journal_mode = WAL");
sqlite.run("PRAGMA foreign_keys = ON");
sqlite.run("PRAGMA busy_timeout = 5000");

export const db = drizzle(sqlite, { schema });

// Migrations run at startup, which suits a single server with one SQLite file.
migrate(db, { migrationsFolder: resolve(process.env.MIGRATIONS_PATH ?? "./drizzle") });
