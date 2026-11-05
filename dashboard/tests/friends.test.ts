import { beforeEach, describe, expect, test } from "bun:test";

import { bitmapSchema, devicePrintRequestSchema } from "@/lib/schemas";
import { db } from "@/server/db.server";
import {
  addFriend,
  friendCodeFor,
  getFriends,
  removeFriend,
  respondToFriend,
  sendNote,
  sendNoteByName,
  setPermission,
} from "@/server/friends.server";
import { createDevice } from "@/server/queries.server";
import { printRequests, user } from "@/server/schema";
import { syncDevice } from "@/server/sync.server";

const STATUS = {
  deviceKind: "sim",
  printer: "preview",
  handyInstalled: false,
  slack: false,
  email: false,
  mode: "idle",
  queue: 0,
  version: "0",
};
const BITMAP = "A".repeat(11232);

function addUser(id: string, name = id) {
  db.insert(user)
    .values({ id, name, email: `${id}@example.com` })
    .run();
  return id;
}

function befriend(a: string, b: string) {
  addFriend(a, friendCodeFor(b));
  const request = getFriends(b).incoming[0];
  respondToFriend(b, request.friendshipId, true);
}

const sync = (deviceId: string, ackedRequests: number[] = []) =>
  syncDevice(deviceId, { status: STATUS, items: [], ackedCommands: [], ackedRequests });

beforeEach(() => {
  db.delete(user).run();
});

describe("becoming friends", () => {
  test("a friend code is stable, private to the owner, and unique", () => {
    addUser("a");
    addUser("b");
    expect(friendCodeFor("a")).toBe(friendCodeFor("a"));
    expect(friendCodeFor("a")).not.toBe(friendCodeFor("b"));
    expect(friendCodeFor("a")).toMatch(/^[A-Z2-9]{4}-[A-Z2-9]{4}$/);
  });

  test("adding by code needs the other person to accept", () => {
    addUser("a", "Ada");
    addUser("b", "Ben");
    expect(addFriend("a", friendCodeFor("b")).ok).toBe(true);
    expect(getFriends("a").friends).toEqual([]);
    expect(getFriends("a").outgoing[0].name).toBe("Ben");
    expect(getFriends("b").incoming[0].name).toBe("Ada");

    respondToFriend("b", getFriends("b").incoming[0].friendshipId, true);
    expect(getFriends("a").friends[0].name).toBe("Ben");
    expect(getFriends("b").friends[0].name).toBe("Ada");
  });

  test("codes work in lower case, since people type them", () => {
    addUser("a");
    addUser("b");
    expect(addFriend("a", friendCodeFor("b").toLowerCase()).ok).toBe(true);
  });

  test("declining removes the request", () => {
    addUser("a");
    addUser("b");
    addFriend("a", friendCodeFor("b"));
    respondToFriend("b", getFriends("b").incoming[0].friendshipId, false);
    expect(getFriends("b").incoming).toEqual([]);
    expect(getFriends("a").outgoing).toEqual([]);
  });

  test("you can't accept your own request", () => {
    addUser("a");
    addUser("b");
    addFriend("a", friendCodeFor("b"));
    respondToFriend("a", getFriends("a").outgoing[0].friendshipId, true);
    expect(getFriends("a").friends).toEqual([]);
  });

  test("a stranger can't answer someone else's request", () => {
    addUser("a");
    addUser("b");
    addUser("c");
    addFriend("a", friendCodeFor("b"));
    respondToFriend("c", getFriends("b").incoming[0].friendshipId, true);
    expect(getFriends("b").friends).toEqual([]);
  });

  test("two people adding each other become friends", () => {
    addUser("a");
    addUser("b");
    addFriend("a", friendCodeFor("b"));
    expect(addFriend("b", friendCodeFor("a")).message).toBe("You're now friends.");
    expect(getFriends("a").friends).toHaveLength(1);
  });

  test.each([
    ["your own code", (a: string) => friendCodeFor(a)],
    ["an unknown code", () => "ZZZZ-ZZZZ"],
  ])("%s is refused", (_, code) => {
    addUser("a");
    expect(addFriend("a", code("a")).ok).toBe(false);
  });

  test("adding twice changes nothing", () => {
    addUser("a");
    addUser("b");
    befriend("a", "b");
    expect(addFriend("a", friendCodeFor("b")).ok).toBe(false);
    expect(getFriends("a").friends).toHaveLength(1);
  });
});

describe("permission to send", () => {
  const friends = () => {
    addUser("a", "Ada");
    addUser("b", "Ben");
    befriend("a", "b");
  };

  test("is off by default, even for friends", () => {
    friends();
    const result = sendNote("a", "b", { title: "Hi" });
    expect(result).toMatchObject({ ok: false, status: 403 });
    expect(getFriends("a").friends[0].canPrintToThem).toBe(false);
  });

  test("only the receiver can grant it, and only in that direction", () => {
    friends();
    setPermission("a", "b", true); // Ada lets Ben print to her.
    expect(sendNote("a", "b", { title: "Hi" }).ok).toBe(false);
    expect(sendNote("b", "a", { title: "Hi" }).ok).toBe(true);
    expect(getFriends("a").friends[0]).toMatchObject({ canPrintToMe: true, canPrintToThem: false });
    expect(getFriends("b").friends[0]).toMatchObject({ canPrintToMe: false, canPrintToThem: true });
  });

  test("strangers can't be granted permission or send", () => {
    addUser("a");
    addUser("b");
    setPermission("a", "b", true);
    expect(getFriends("b").friends).toEqual([]);
    expect(sendNote("b", "a", { title: "Hi" })).toMatchObject({ ok: false, status: 404 });
  });

  test("taking it back stops new notes and ones not yet delivered", () => {
    friends();
    const device = createDevice("b", "Desk");
    setPermission("b", "a", true);
    sendNote("a", "b", { title: "Queued" });
    setPermission("b", "a", false);
    expect(sendNote("a", "b", { title: "New" }).ok).toBe(false);
    expect(sync(device.id).requests).toEqual([]);
  });

  test("there's a limit per hour, so a friend can't empty your paper", () => {
    friends();
    setPermission("b", "a", true);
    for (let i = 0; i < 30; i++) expect(sendNote("a", "b", { title: `${i}` }).ok).toBe(true);
    expect(sendNote("a", "b", { title: "one more" })).toMatchObject({ ok: false, status: 429 });
  });

  test("removing a friend ends everything both ways", () => {
    friends();
    setPermission("a", "b", true);
    setPermission("b", "a", true);
    sendNote("a", "b", { title: "Pending" });
    removeFriend("a", "b");
    expect(getFriends("a").friends).toEqual([]);
    expect(getFriends("b").friends).toEqual([]);
    expect(db.select().from(printRequests).all()).toEqual([]);
    befriend("a", "b");
    expect(sendNote("a", "b", { title: "Hi" }).ok).toBe(false); // Permission doesn't come back.
  });
});

describe("delivery", () => {
  const ready = () => {
    addUser("a", "Ada");
    addUser("b", "Ben");
    befriend("a", "b");
    setPermission("b", "a", true);
    return createDevice("b", "Desk");
  };

  test("a note reaches the friend's device with its design and the sender's real name", () => {
    const device = ready();
    sendNote("a", "b", { title: "Hi", detail: "there", bitmap: BITMAP });
    expect(sync(device.id).requests[0]).toMatchObject({
      sender: "Ada",
      title: "Hi",
      detail: "there",
      bitmap: BITMAP,
    });
  });

  test("it repeats until acknowledged, then stops", () => {
    const device = ready();
    sendNote("a", "b", { title: "Hi" });
    const [first] = sync(device.id).requests;
    expect(sync(device.id).requests).toHaveLength(1);
    expect(getFriends("a").sent[0].deliveredAt).toBeNull();
    expect(sync(device.id, [first.id]).requests).toEqual([]);
    expect(getFriends("a").sent[0].deliveredAt).not.toBeNull();
  });

  test("with two devices, only one receives it", () => {
    const one = ready();
    const two = createDevice("b", "Other desk");
    sendNote("a", "b", { title: "Hi" });
    expect(sync(one.id).requests).toHaveLength(1);
    expect(sync(two.id).requests).toEqual([]);
  });

  test("a device can't acknowledge or receive someone else's notes", () => {
    const device = ready();
    const stranger = createDevice("a", "Ada's desk");
    sendNote("a", "b", { title: "Hi" });
    const [note] = sync(device.id).requests;
    expect(sync(stranger.id, [note.id]).requests).toEqual([]);
    expect(sync(device.id).requests).toHaveLength(1);
  });
});

describe("sending by name, as an agent does", () => {
  const setup = () => {
    addUser("a", "Ada");
    addUser("b", "Ben Berg");
    addUser("c", "Ben Hansen");
    befriend("a", "b");
    befriend("a", "c");
    setPermission("b", "a", true);
  };

  test("an exact name, a partial name, or an id all work", () => {
    setup();
    expect(sendNoteByName("a", "ben berg", { title: "x" }).ok).toBe(true);
    expect(sendNoteByName("a", "Berg", { title: "x" }).ok).toBe(true);
    expect(sendNoteByName("a", "b", { title: "x" }).ok).toBe(true);
  });

  test("an ambiguous name asks which one rather than guessing", () => {
    setup();
    const result = sendNoteByName("a", "Ben", { title: "x" });
    expect(result).toMatchObject({ ok: false, status: 409 });
    if (!result.ok) expect(result.error).toContain("Ben Hansen");
  });

  test("names of people who aren't friends find nothing", () => {
    setup();
    addUser("d", "Dana");
    expect(sendNoteByName("a", "Dana", { title: "x" })).toMatchObject({ ok: false, status: 404 });
  });
});

describe("what a note may contain", () => {
  test("a design must be exactly one 312x216 grid", () => {
    expect(bitmapSchema.safeParse(BITMAP).success).toBe(true);
    expect(bitmapSchema.safeParse("A".repeat(11231)).success).toBe(false);
    expect(bitmapSchema.safeParse("!".repeat(11232)).success).toBe(false);
  });

  test("a note needs a recipient and text", () => {
    expect(devicePrintRequestSchema.safeParse({ to: "Ben", title: "Hi" }).success).toBe(true);
    expect(devicePrintRequestSchema.safeParse({ to: "Ben", title: "  " }).success).toBe(false);
    expect(devicePrintRequestSchema.safeParse({ title: "Hi" }).success).toBe(false);
  });
});
