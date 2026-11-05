import { randomInt } from "node:crypto";
import { and, asc, count, desc, eq, gte, inArray, isNull, or, sql } from "drizzle-orm";

import { db } from "./db.server";
import { devices, friendships, printPermissions, printRequests, profiles, user } from "./schema";

const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // No 0/O or 1/I, since people type these.
const MAX_NOTES_PER_HOUR = 30;
const HOUR_MS = 3_600_000;

export type NoteInput = { title: string; detail?: string; bitmap?: string | null };

export type SendResult =
  | { ok: true; message: string }
  | { ok: false; status: 403 | 404 | 409 | 429; error: string };

function newFriendCode() {
  const part = () =>
    Array.from({ length: 4 }, () => CODE_ALPHABET[randomInt(CODE_ALPHABET.length)]).join("");
  return `${part()}-${part()}`;
}

export function friendCodeFor(userId: string) {
  const existing = db.select().from(profiles).where(eq(profiles.userId, userId)).get();
  if (existing) return existing.friendCode;
  const friendCode = newFriendCode();
  db.insert(profiles).values({ userId, friendCode }).onConflictDoNothing().run();
  return (
    db.select().from(profiles).where(eq(profiles.userId, userId)).get()?.friendCode ?? friendCode
  );
}

function betweenUsers(a: string, b: string) {
  return or(
    and(eq(friendships.requesterId, a), eq(friendships.addresseeId, b)),
    and(eq(friendships.requesterId, b), eq(friendships.addresseeId, a)),
  );
}

function areFriends(a: string, b: string) {
  const row = db
    .select({ status: friendships.status })
    .from(friendships)
    .where(betweenUsers(a, b))
    .get();
  return row?.status === "accepted";
}

export function getFriends(userId: string) {
  const rows = db
    .select()
    .from(friendships)
    .where(or(eq(friendships.requesterId, userId), eq(friendships.addresseeId, userId)))
    .orderBy(asc(friendships.createdAt))
    .all();

  const otherIds = rows.map((row) =>
    row.requesterId === userId ? row.addresseeId : row.requesterId,
  );
  const people = otherIds.length
    ? db.select({ id: user.id, name: user.name }).from(user).where(inArray(user.id, otherIds)).all()
    : [];
  const nameOf = new Map(people.map((person) => [person.id, person.name]));

  const permissions = db
    .select()
    .from(printPermissions)
    .where(or(eq(printPermissions.grantorId, userId), eq(printPermissions.granteeId, userId)))
    .all();
  const iAllow = new Set(permissions.filter((p) => p.grantorId === userId).map((p) => p.granteeId));
  const theyAllow = new Set(
    permissions.filter((p) => p.granteeId === userId).map((p) => p.grantorId),
  );

  const friends = [];
  const incoming = [];
  const outgoing = [];
  for (const row of rows) {
    const otherId = row.requesterId === userId ? row.addresseeId : row.requesterId;
    const name = nameOf.get(otherId) ?? "Someone";
    if (row.status === "accepted") {
      friends.push({
        id: otherId,
        name,
        canPrintToMe: iAllow.has(otherId),
        canPrintToThem: theyAllow.has(otherId),
      });
    } else if (row.addresseeId === userId) {
      incoming.push({ friendshipId: row.id, name });
    } else {
      outgoing.push({ friendshipId: row.id, name });
    }
  }

  const sent = db
    .select({
      id: printRequests.id,
      title: printRequests.title,
      recipient: user.name,
      createdAt: printRequests.createdAt,
      deliveredAt: printRequests.deliveredAt,
    })
    .from(printRequests)
    .innerJoin(user, eq(printRequests.recipientId, user.id))
    .where(eq(printRequests.senderId, userId))
    .orderBy(desc(printRequests.createdAt), desc(printRequests.id))
    .limit(10)
    .all();

  return { code: friendCodeFor(userId), friends, incoming, outgoing, sent };
}

export function addFriend(userId: string, rawCode: string): { ok: boolean; message: string } {
  const code = rawCode.trim().toUpperCase();
  const target = db.select().from(profiles).where(eq(profiles.friendCode, code)).get();
  if (!target) return { ok: false, message: "No one has that code. Check it and try again." };
  if (target.userId === userId) return { ok: false, message: "That's your own code." };

  const existing = db.select().from(friendships).where(betweenUsers(userId, target.userId)).get();
  if (existing?.status === "accepted") return { ok: false, message: "You're already friends." };
  if (existing && existing.requesterId === userId) {
    return { ok: false, message: "Your request is still waiting for an answer." };
  }
  if (existing) {
    // They had already asked you, so adding them back is the same as accepting.
    db.update(friendships).set({ status: "accepted" }).where(eq(friendships.id, existing.id)).run();
    return { ok: true, message: "You're now friends." };
  }
  db.insert(friendships)
    .values({ requesterId: userId, addresseeId: target.userId, status: "pending" })
    .run();
  return { ok: true, message: "Friend request sent." };
}

/** Only the person who received the request can answer it. */
export function respondToFriend(userId: string, friendshipId: number, accept: boolean) {
  const where = and(
    eq(friendships.id, friendshipId),
    eq(friendships.addresseeId, userId),
    eq(friendships.status, "pending"),
  );
  if (accept) db.update(friendships).set({ status: "accepted" }).where(where).run();
  else db.delete(friendships).where(where).run();
}

/** Also cancels your own unanswered requests, and takes back every permission both ways. */
export function removeFriend(userId: string, friendId: string) {
  db.transaction((tx) => {
    tx.delete(friendships).where(betweenUsers(userId, friendId)).run();
    tx.delete(printPermissions)
      .where(
        or(
          and(eq(printPermissions.grantorId, userId), eq(printPermissions.granteeId, friendId)),
          and(eq(printPermissions.grantorId, friendId), eq(printPermissions.granteeId, userId)),
        ),
      )
      .run();
    tx.delete(printRequests)
      .where(
        and(
          isNull(printRequests.deliveredAt),
          or(
            and(eq(printRequests.senderId, userId), eq(printRequests.recipientId, friendId)),
            and(eq(printRequests.senderId, friendId), eq(printRequests.recipientId, userId)),
          ),
        ),
      )
      .run();
  });
}

/** You only ever change who may print to you. Nobody can grant themselves access. */
export function setPermission(userId: string, friendId: string, allowed: boolean) {
  const mine = and(
    eq(printPermissions.grantorId, userId),
    eq(printPermissions.granteeId, friendId),
  );
  if (!allowed) {
    db.delete(printPermissions).where(mine).run();
    return;
  }
  if (!areFriends(userId, friendId)) return;
  db.insert(printPermissions)
    .values({ grantorId: userId, granteeId: friendId })
    .onConflictDoNothing()
    .run();
}

export function sendNote(senderId: string, recipientId: string, note: NoteInput): SendResult {
  if (!areFriends(senderId, recipientId)) {
    return { ok: false, status: 404, error: "You aren't friends with them." };
  }
  const recipient = db.select({ name: user.name }).from(user).where(eq(user.id, recipientId)).get();
  const name = recipient?.name ?? "They";
  const allowed = db
    .select({ id: printPermissions.grantorId })
    .from(printPermissions)
    .where(
      and(eq(printPermissions.grantorId, recipientId), eq(printPermissions.granteeId, senderId)),
    )
    .get();
  if (!allowed) {
    return {
      ok: false,
      status: 403,
      error: `${name} hasn't given you permission to print to them yet.`,
    };
  }

  const lastHour = new Date(Date.now() - HOUR_MS);
  const recent =
    db
      .select({ value: count() })
      .from(printRequests)
      .where(
        and(
          eq(printRequests.senderId, senderId),
          eq(printRequests.recipientId, recipientId),
          gte(printRequests.createdAt, lastHour),
        ),
      )
      .get()?.value ?? 0;
  if (recent >= MAX_NOTES_PER_HOUR) {
    return {
      ok: false,
      status: 429,
      error: `That's plenty for ${name} this hour. Try again later.`,
    };
  }

  db.insert(printRequests)
    .values({
      senderId,
      recipientId,
      title: note.title,
      detail: note.detail ?? "",
      bitmap: note.bitmap ?? null,
    })
    .run();
  return {
    ok: true,
    message: `Sent to ${name}. They'll approve it on their device before it prints.`,
  };
}

/** For agents, which know a friend by name. */
export function sendNoteByName(senderId: string, to: string, note: NoteInput): SendResult {
  const friends = getFriends(senderId).friends;
  const exact = friends.filter((friend) => friend.id === to);
  const wanted = to.toLowerCase();
  const named = friends.filter((friend) => friend.name.toLowerCase() === wanted);
  const partial = friends.filter((friend) => friend.name.toLowerCase().includes(wanted));
  const matches = exact.length ? exact : named.length ? named : partial;
  if (matches.length === 0) {
    return {
      ok: false,
      status: 404,
      error: `You have no friend called ${to}. list_friends shows who you have.`,
    };
  }
  if (matches.length > 1) {
    const options = matches.map((friend) => `${friend.name} (${friend.id})`).join(", ");
    return {
      ok: false,
      status: 409,
      error: `More than one friend matches ${to}: ${options}. Send to an id.`,
    };
  }
  return sendNote(senderId, matches[0].id, note);
}

type Tx = Parameters<Parameters<typeof db.transaction>[0]>[0];

/** Called during a device's sync. Permission is checked now too: taking it back stops what's queued. */
export function requestsForDevice(tx: Tx, deviceId: string, acked: number[]) {
  const device = tx
    .select({ userId: devices.userId })
    .from(devices)
    .where(eq(devices.id, deviceId))
    .get();
  if (!device) return [];

  if (acked.length > 0) {
    tx.update(printRequests)
      .set({ deliveredAt: new Date() })
      .where(
        and(
          inArray(printRequests.id, acked),
          eq(printRequests.recipientId, device.userId),
          eq(printRequests.claimedDeviceId, deviceId),
        ),
      )
      .run();
  }

  const pending = tx
    .select({
      id: printRequests.id,
      title: printRequests.title,
      detail: printRequests.detail,
      bitmap: printRequests.bitmap,
      sender: user.name,
    })
    .from(printRequests)
    .innerJoin(user, eq(printRequests.senderId, user.id))
    .innerJoin(
      printPermissions,
      and(
        eq(printPermissions.grantorId, printRequests.recipientId),
        eq(printPermissions.granteeId, printRequests.senderId),
      ),
    )
    .where(
      and(
        eq(printRequests.recipientId, device.userId),
        isNull(printRequests.deliveredAt),
        or(isNull(printRequests.claimedDeviceId), eq(printRequests.claimedDeviceId, deviceId)),
      ),
    )
    .orderBy(asc(printRequests.id))
    .limit(10)
    .all();

  if (pending.length > 0) {
    tx.update(printRequests)
      .set({ claimedDeviceId: deviceId })
      .where(
        and(
          inArray(
            printRequests.id,
            pending.map((request) => request.id),
          ),
          sql`${printRequests.claimedDeviceId} IS NULL`,
        ),
      )
      .run();
  }
  return pending;
}
