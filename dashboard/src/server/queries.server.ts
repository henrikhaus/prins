import { and, asc, count, desc, eq, gte, inArray, isNull, ne, or, sql } from "drizzle-orm";

import type { CommandAction } from "./schema";
import type { HistorySearch } from "@/lib/schemas";

import { TIME_ZONE } from "@/lib/format";

import { db } from "./db.server";
import { commands, devices, items } from "./schema";
import { newDeviceToken } from "./sync.server";

export const ONLINE_WINDOW_MS = 30_000;
const HISTORY_PAGE_SIZE = 25;
const CHART_DAYS = 14;
const DAY_MS = 86_400_000;

const dayKey = new Intl.DateTimeFormat("en-CA", {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** Every query below filters on this list, which is what keeps accounts apart. */
function deviceIdsFor(userId: string) {
  return db
    .select({ id: devices.id })
    .from(devices)
    .where(eq(devices.userId, userId))
    .all()
    .map((device) => device.id);
}

export type DayBucket = {
  day: string;
  printed: number;
  dismissed: number;
  ignored: number;
};

export function getOverview(userId: string, now = Date.now()) {
  const deviceIds = deviceIdsFor(userId);
  const since = new Date(now - CHART_DAYS * DAY_MS);
  const rows = db
    .select({
      source: items.source,
      status: items.status,
      engine: items.engine,
      createdAt: items.createdAt,
    })
    .from(items)
    .where(and(inArray(items.deviceId, deviceIds), gte(items.createdAt, since)))
    .all();

  const buckets = new Map<string, DayBucket>();
  for (let offset = CHART_DAYS - 1; offset >= 0; offset--) {
    const day = dayKey.format(new Date(now - offset * DAY_MS));
    buckets.set(day, { day, printed: 0, dismissed: 0, ignored: 0 });
  }

  const totals = { received: 0, printed: 0, dismissed: 0, ignored: 0, queued: 0 };
  const sources = new Map<string, number>();
  for (const row of rows) {
    totals.received += 1;
    totals[row.status] += 1;
    sources.set(row.source, (sources.get(row.source) ?? 0) + 1);
    if (row.status === "queued") continue;
    const bucket = buckets.get(dayKey.format(row.createdAt));
    if (bucket) bucket[row.status] += 1;
  }

  const decided = totals.printed + totals.dismissed;
  return {
    days: CHART_DAYS,
    totals,
    // How often the model's suggestion was good enough to print.
    keepRate: decided > 0 ? Math.round((totals.printed / decided) * 100) : null,
    chart: [...buckets.values()],
    sources: [...sources.entries()]
      .map(([source, value]) => ({ source, value }))
      .sort((a, b) => b.value - a.value),
    hasDemoDevice: getDevices(userId).some((device) => device.isDemo),
  };
}

export function getQueue(userId: string) {
  const deviceIds = deviceIdsFor(userId);
  const rows = db
    .select({
      id: items.id,
      source: items.source,
      sender: items.sender,
      title: items.title,
      detail: items.detail,
      priority: items.priority,
      due: items.due,
      createdAt: items.createdAt,
      bitmap: items.bitmap,
      deviceName: devices.name,
      pendingAction: commands.action,
    })
    .from(items)
    .innerJoin(devices, eq(items.deviceId, devices.id))
    .leftJoin(commands, and(eq(commands.itemId, items.id), isNull(commands.ackedAt)))
    .where(and(inArray(items.deviceId, deviceIds), eq(items.status, "queued")))
    .orderBy(
      sql`CASE ${items.priority} WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END`,
      asc(items.createdAt),
    )
    .all();
  return rows;
}

export type DecideResult = "sent" | "not_found";

export function decideItem(userId: string, itemId: number, action: CommandAction): DecideResult {
  return db.transaction((tx) => {
    const item = tx
      .select({ id: items.id, deviceId: items.deviceId, isDemo: devices.isDemo })
      .from(items)
      .innerJoin(devices, eq(items.deviceId, devices.id))
      .where(
        and(
          eq(items.id, itemId),
          eq(devices.userId, userId),
          eq(items.status, "queued"),
          isNull(devices.revokedAt),
        ),
      )
      .get();
    if (!item) return "not_found";

    // A sample device has nothing to answer a command, so decide right away.
    if (item.isDemo) {
      tx.update(items)
        .set({ status: action === "print" ? "printed" : "dismissed", decidedAt: new Date() })
        .where(eq(items.id, itemId))
        .run();
      return "sent";
    }

    // A second click on a note already waiting for the device changes nothing.
    const pending = tx
      .select({ id: commands.id })
      .from(commands)
      .where(and(eq(commands.itemId, itemId), isNull(commands.ackedAt)))
      .get();
    if (!pending) {
      tx.insert(commands).values({ deviceId: item.deviceId, itemId, action }).run();
    }
    return "sent";
  });
}

export function getHistory(userId: string, search: HistorySearch) {
  const deviceIds = deviceIdsFor(userId);
  const conditions = [inArray(items.deviceId, deviceIds), ne(items.status, "queued")];
  if (search.status !== "all") conditions.push(eq(items.status, search.status));
  if (search.source !== "all") conditions.push(eq(items.source, search.source));
  if (search.search) {
    const term = `%${search.search.replace(/[%_\\]/g, "\\$&")}%`;
    const match = or(
      sql`${items.title} LIKE ${term} ESCAPE '\\'`,
      sql`${items.sender} LIKE ${term} ESCAPE '\\'`,
      sql`${items.detail} LIKE ${term} ESCAPE '\\'`,
    );
    if (match) conditions.push(match);
  }
  const where = and(...conditions);

  const total = db.select({ value: count() }).from(items).where(where).get()?.value ?? 0;
  const rows = db
    .select({
      id: items.id,
      source: items.source,
      sender: items.sender,
      title: items.title,
      status: items.status,
      engine: items.engine,
      createdAt: items.createdAt,
      decidedAt: items.decidedAt,
    })
    .from(items)
    .where(where)
    .orderBy(desc(items.createdAt), desc(items.id))
    .limit(HISTORY_PAGE_SIZE)
    .offset((search.page - 1) * HISTORY_PAGE_SIZE)
    .all();
  const sources = db
    .selectDistinct({ source: items.source })
    .from(items)
    .where(inArray(items.deviceId, deviceIds))
    .orderBy(asc(items.source))
    .all()
    .map((row) => row.source);

  return { rows, total, pageSize: HISTORY_PAGE_SIZE, sources };
}

export function getDevices(userId: string, now = Date.now()) {
  return db
    .select({
      id: devices.id,
      name: devices.name,
      status: devices.status,
      isDemo: devices.isDemo,
      createdAt: devices.createdAt,
      lastSeenAt: devices.lastSeenAt,
    })
    .from(devices)
    .where(and(eq(devices.userId, userId), isNull(devices.revokedAt)))
    .orderBy(asc(devices.createdAt))
    .all()
    .map((device) => ({
      ...device,
      online:
        device.isDemo ||
        (device.lastSeenAt !== null && now - device.lastSeenAt.getTime() < ONLINE_WINDOW_MS),
    }));
}

export function createDevice(userId: string, name: string) {
  const { token, tokenHash } = newDeviceToken();
  const device = db.insert(devices).values({ userId, name, tokenHash }).returning().get();
  // The only time the token is available. It is shown once and never stored.
  return { id: device.id, name: device.name, token };
}

export function revokeDevice(userId: string, deviceId: string) {
  db.update(devices)
    .set({ revokedAt: new Date() })
    .where(and(eq(devices.id, deviceId), eq(devices.userId, userId)))
    .run();
}
