import { beforeEach, describe, expect, test } from "bun:test";
import { eq } from "drizzle-orm";

import type { SyncRequest } from "@/lib/schemas";

import { formatDateTime, formatDay, niceCeiling } from "@/lib/format";
import { historySchema, syncRequestSchema } from "@/lib/schemas";
import { db } from "@/server/db.server";
import {
  createDevice,
  decideItem,
  getDevices,
  getHistory,
  getOverview,
  getQueue,
  revokeDevice,
} from "@/server/queries.server";
import { commands, devices, items, user } from "@/server/schema";
import { authenticateDevice, hashToken, syncDevice } from "@/server/sync.server";

const STATUS: SyncRequest["status"] = {
  deviceKind: "atech",
  printer: "preview",
  handyInstalled: true,
  slack: true,
  email: false,
  mode: "idle",
  queue: 1,
  version: "0.1.0",
};

const note = (
  localId: number,
  over: Partial<SyncRequest["items"][number]> = {},
): SyncRequest["items"][number] => ({
  localId,
  source: "slack",
  sender: "Maria",
  title: `Task ${localId}`,
  detail: "",
  priority: "normal",
  due: "",
  status: "queued",
  engine: "model",
  createdAt: Date.now(),
  decidedAt: null,
  ...over,
});

const sync = (
  deviceId: string,
  itemList: SyncRequest["items"] = [],
  ackedCommands: number[] = [],
) => syncDevice(deviceId, { status: STATUS, items: itemList, ackedCommands, ackedRequests: [] });

function addUser(id: string) {
  db.insert(user)
    .values({ id, name: id, email: `${id}@example.com` })
    .run();
  return id;
}

function itemId(deviceId: string, localId: number) {
  const row = db
    .select()
    .from(items)
    .where(eq(items.deviceId, deviceId))
    .all()
    .find((i) => i.localId === localId);
  if (!row) throw new Error("no such item");
  return row.id;
}

beforeEach(() => {
  db.delete(user).run();
});

describe("device tokens", () => {
  test("a new token authenticates, and only its hash is stored", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    expect(authenticateDevice(`Bearer ${device.token}`)?.id).toBe(device.id);
    const stored = db.select().from(devices).where(eq(devices.id, device.id)).get();
    expect(stored?.tokenHash).toBe(hashToken(device.token));
    expect(JSON.stringify(stored)).not.toContain(device.token);
  });

  test.each([[null], [""], ["Bearer nope"], ["Bearer prins_wrong"], ["prins_wrong"]])(
    "rejects %p",
    (header) => {
      expect(authenticateDevice(header)).toBeNull();
    },
  );

  test("a revoked device can no longer sync", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    revokeDevice("a", device.id);
    expect(authenticateDevice(`Bearer ${device.token}`)).toBeNull();
    expect(getDevices("a")).toEqual([]);
  });
});

describe("sync", () => {
  test("stores items and device status, and marks the device online", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    sync(device.id, [note(1)]);
    expect(getQueue("a").map((i) => i.title)).toEqual(["Task 1"]);
    const [row] = getDevices("a");
    expect(row.online).toBe(true);
    expect(row.status?.slack).toBe(true);
  });

  test("a device goes offline when it stops syncing", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    sync(device.id);
    expect(getDevices("a", Date.now() + 60_000)[0].online).toBe(false);
  });

  test("sending the same item twice updates it instead of duplicating", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    sync(device.id, [note(1)]);
    sync(device.id, [note(1, { status: "printed", decidedAt: Date.now() })]);
    expect(getQueue("a")).toEqual([]);
    expect(db.select().from(items).all()).toHaveLength(1);
  });

  test("two devices can use the same local id", () => {
    addUser("a");
    const first = createDevice("a", "One");
    const second = createDevice("a", "Two");
    sync(first.id, [note(1)]);
    sync(second.id, [note(1)]);
    expect(getQueue("a")).toHaveLength(2);
  });

  test("a payload with raw message text is not stored", () => {
    const parsed = syncRequestSchema.parse({
      status: STATUS,
      items: [{ ...note(1), rawText: "secret email body" }],
      ackedCommands: [],
    });
    expect(JSON.stringify(parsed)).not.toContain("secret email body");
  });

  test("oversized or malformed payloads are refused", () => {
    const tooMany = Array.from({ length: 201 }, (_, i) => note(i + 1));
    expect(
      syncRequestSchema.safeParse({ status: STATUS, items: tooMany, ackedCommands: [] }).success,
    ).toBe(false);
    expect(
      syncRequestSchema.safeParse({
        status: STATUS,
        items: [note(1, { status: "hacked" as never })],
        ackedCommands: [],
      }).success,
    ).toBe(false);
  });
});

describe("deciding on the web", () => {
  test("a decision reaches the device and stops once acknowledged", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    sync(device.id, [note(7)]);
    expect(decideItem("a", itemId(device.id, 7), "print")).toBe("sent");

    const first = sync(device.id).commands;
    expect(first).toHaveLength(1);
    expect(first[0]).toMatchObject({ action: "print", localId: 7 });
    expect(getQueue("a")[0].pendingAction).toBe("print");

    // Sent again until acknowledged, in case the response was lost.
    expect(sync(device.id).commands).toHaveLength(1);
    expect(sync(device.id, [], [first[0].id]).commands).toEqual([]);
  });

  test("a second click does not queue a second print", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    sync(device.id, [note(1)]);
    const id = itemId(device.id, 1);
    decideItem("a", id, "print");
    decideItem("a", id, "dismiss");
    expect(db.select().from(commands).all()).toHaveLength(1);
  });

  test("a note already decided on the device cannot be decided again", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    sync(device.id, [note(1, { status: "dismissed", decidedAt: Date.now() })]);
    expect(decideItem("a", itemId(device.id, 1), "print")).toBe("not_found");
  });
});

describe("sample devices", () => {
  test("a decision applies at once, because nothing would ever answer a command", () => {
    addUser("a");
    const device = createDevice("a", "Demo");
    db.update(devices).set({ isDemo: true }).where(eq(devices.id, device.id)).run();
    sync(device.id, [note(1)]);
    expect(decideItem("a", itemId(device.id, 1), "print")).toBe("sent");
    expect(getQueue("a")).toEqual([]);
    expect(db.select().from(commands).all()).toEqual([]);
    expect(getOverview("a").totals.printed).toBe(1);
  });
});

describe("accounts are kept apart", () => {
  test("one user cannot see or act on another's data", () => {
    addUser("a");
    addUser("b");
    const device = createDevice("a", "Desk");
    sync(device.id, [note(1), note(2, { status: "printed", decidedAt: Date.now() })]);
    const id = itemId(device.id, 1);

    expect(getQueue("b")).toEqual([]);
    expect(getDevices("b")).toEqual([]);
    expect(getOverview("b").totals.received).toBe(0);
    expect(getHistory("b", historySchema.parse({})).rows).toEqual([]);
    expect(decideItem("b", id, "print")).toBe("not_found");
    expect(db.select().from(commands).all()).toEqual([]);

    revokeDevice("b", device.id);
    expect(getDevices("a")).toHaveLength(1);
  });

  test("one device cannot acknowledge another device's commands", () => {
    addUser("a");
    addUser("b");
    const mine = createDevice("a", "Mine");
    const theirs = createDevice("b", "Theirs");
    sync(mine.id, [note(1)]);
    decideItem("a", itemId(mine.id, 1), "print");
    const [command] = sync(mine.id).commands;
    sync(theirs.id, [], [command.id]);
    expect(sync(mine.id).commands).toHaveLength(1);
  });
});

describe("overview", () => {
  test("adds up outcomes, sources and the kept rate", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    const decidedAt = Date.now();
    sync(device.id, [
      note(1),
      note(2, { status: "printed", decidedAt }),
      note(3, { status: "printed", decidedAt, source: "email" }),
      note(4, { status: "printed", decidedAt }),
      note(5, { status: "dismissed", decidedAt }),
      note(6, { status: "ignored", decidedAt }),
    ]);
    const overview = getOverview("a");
    expect(overview.totals).toEqual({
      received: 6,
      printed: 3,
      dismissed: 1,
      ignored: 1,
      queued: 1,
    });
    expect(overview.keepRate).toBe(75);
    expect(overview.sources[0]).toEqual({ source: "slack", value: 5 });
    const today = overview.chart.at(-1);
    expect(today).toMatchObject({ printed: 3, dismissed: 1, ignored: 1 });
    expect(overview.chart).toHaveLength(14);
  });

  test("with no decisions there is no kept rate, rather than a misleading 0%", () => {
    addUser("a");
    expect(getOverview("a").keepRate).toBeNull();
  });

  test("items older than the window are left out", () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    sync(device.id, [note(1, { createdAt: Date.now() - 30 * 86_400_000 })]);
    expect(getOverview("a").totals.received).toBe(0);
  });
});

describe("history", () => {
  const seed = () => {
    addUser("a");
    const device = createDevice("a", "Desk");
    const decidedAt = Date.now();
    sync(device.id, [
      note(1),
      note(2, { status: "printed", decidedAt, title: "Call the bank" }),
      note(3, { status: "dismissed", decidedAt, title: "Call 100% of vendors", source: "email" }),
    ]);
  };

  test("leaves out what is still queued", () => {
    seed();
    expect(getHistory("a", historySchema.parse({})).total).toBe(2);
  });

  test("filters by outcome and source", () => {
    seed();
    expect(getHistory("a", historySchema.parse({ status: "printed" })).rows[0].title).toBe(
      "Call the bank",
    );
    expect(getHistory("a", historySchema.parse({ source: "email" })).total).toBe(1);
  });

  test("search treats % and _ as plain characters", () => {
    seed();
    expect(getHistory("a", historySchema.parse({ search: "100%" })).total).toBe(1);
    expect(getHistory("a", historySchema.parse({ search: "%" })).total).toBe(1);
    expect(getHistory("a", historySchema.parse({ search: "bank" })).total).toBe(1);
  });

  test("bad filter values fall back instead of failing", () => {
    expect(historySchema.parse({ status: "nope", page: -3 })).toMatchObject({
      status: "all",
      page: 1,
    });
  });
});

describe("dates", () => {
  test("use one fixed format and zone, so server and browser agree", () => {
    expect(formatDateTime(new Date("2026-11-05T16:00:00Z"))).toBe("5 Nov, 17:00");
    expect(formatDateTime(new Date("2026-07-01T22:30:00Z"))).toBe("2 Jul, 00:30");
    expect(formatDay("2026-11-05")).toBe("5 Nov");
  });
});

describe("chart scale", () => {
  test.each([
    [0, 4],
    [3, 4],
    [7, 8],
    [11, 20],
    [26, 30],
    [51, 60],
    [100, 100],
  ])("%d rounds up to %d", (value, expected) => {
    expect(niceCeiling(value)).toBe(expected);
  });
});
