import { createHash, randomBytes } from "node:crypto";
import { and, asc, eq, inArray, isNull } from "drizzle-orm";

import type { SyncRequest } from "@/lib/schemas";

import { db } from "./db.server";
import { requestsForDevice } from "./friends.server";
import { commands, devices, items } from "./schema";

export const hashToken = (token: string) => createHash("sha256").update(token).digest("hex");

/** Only the hash is stored, so a leaked database does not expose device tokens. */
export function newDeviceToken() {
  const token = `prins_${randomBytes(32).toString("base64url")}`;
  return { token, tokenHash: hashToken(token) };
}

export function authenticateDevice(authorization: string | null) {
  const token = authorization?.match(/^Bearer (prins_[\w-]+)$/)?.[1];
  if (!token) return null;
  const device = db
    .select()
    .from(devices)
    .where(eq(devices.tokenHash, hashToken(token)))
    .get();
  return device && !device.revokedAt ? device : null;
}

/** Stores what the device reports, and returns the web decisions it still has to carry out. */
export function syncDevice(deviceId: string, request: SyncRequest) {
  return db.transaction((tx) => {
    tx.update(devices)
      .set({ lastSeenAt: new Date(), status: request.status })
      .where(eq(devices.id, deviceId))
      .run();

    for (const item of request.items) {
      const values = {
        source: item.source,
        sender: item.sender,
        title: item.title,
        detail: item.detail,
        priority: item.priority,
        due: item.due,
        status: item.status,
        engine: item.engine,
        createdAt: new Date(item.createdAt),
        decidedAt: item.decidedAt ? new Date(item.decidedAt) : null,
        bitmap: item.bitmap ?? null,
      };
      tx.insert(items)
        .values({ deviceId, localId: item.localId, ...values })
        .onConflictDoUpdate({ target: [items.deviceId, items.localId], set: values })
        .run();
    }

    if (request.ackedCommands.length > 0) {
      // Scoped to this device: one device cannot acknowledge another's commands.
      tx.update(commands)
        .set({ ackedAt: new Date() })
        .where(and(eq(commands.deviceId, deviceId), inArray(commands.id, request.ackedCommands)))
        .run();
    }

    const pending = tx
      .select({ id: commands.id, action: commands.action, localId: items.localId })
      .from(commands)
      .innerJoin(items, eq(commands.itemId, items.id))
      .where(and(eq(commands.deviceId, deviceId), isNull(commands.ackedAt)))
      .orderBy(asc(commands.id))
      .limit(20)
      .all();

    return { commands: pending, requests: requestsForDevice(tx, deviceId, request.ackedRequests) };
  });
}
