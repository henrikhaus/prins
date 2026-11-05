import { relations } from "drizzle-orm";
import { index, integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

const createdAt = () =>
  integer("created_at", { mode: "timestamp_ms" })
    .notNull()
    .$defaultFn(() => new Date());

// --- BetterAuth's tables ---------------------------------------------------------------

export const user = sqliteTable("user", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: integer("email_verified", { mode: "boolean" }).notNull().default(false),
  image: text("image"),
  createdAt: createdAt(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" })
    .notNull()
    .$defaultFn(() => new Date()),
});

export const session = sqliteTable("session", {
  id: text("id").primaryKey(),
  expiresAt: integer("expires_at", { mode: "timestamp_ms" }).notNull(),
  token: text("token").notNull().unique(),
  createdAt: createdAt(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" })
    .notNull()
    .$defaultFn(() => new Date()),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  userId: text("user_id")
    .notNull()
    .references(() => user.id, { onDelete: "cascade" }),
});

export const account = sqliteTable("account", {
  id: text("id").primaryKey(),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  userId: text("user_id")
    .notNull()
    .references(() => user.id, { onDelete: "cascade" }),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  idToken: text("id_token"),
  accessTokenExpiresAt: integer("access_token_expires_at", { mode: "timestamp_ms" }),
  refreshTokenExpiresAt: integer("refresh_token_expires_at", { mode: "timestamp_ms" }),
  scope: text("scope"),
  password: text("password"),
  createdAt: createdAt(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" })
    .notNull()
    .$defaultFn(() => new Date()),
});

export const verification = sqliteTable("verification", {
  id: text("id").primaryKey(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: integer("expires_at", { mode: "timestamp_ms" }).notNull(),
  createdAt: createdAt(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" })
    .notNull()
    .$defaultFn(() => new Date()),
});

// --- Prins ------------------------------------------------------------------------------

export type DeviceStatus = {
  deviceKind: string;
  printer: string;
  handyInstalled: boolean;
  slack: boolean;
  email: boolean;
  mode: string;
  queue: number;
  version: string;
};

export const devices = sqliteTable(
  "devices",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    userId: text("user_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    tokenHash: text("token_hash").notNull().unique(),
    status: text("status", { mode: "json" }).$type<DeviceStatus>(),
    isDemo: integer("is_demo", { mode: "boolean" }).notNull().default(false),
    createdAt: createdAt(),
    lastSeenAt: integer("last_seen_at", { mode: "timestamp_ms" }),
    // Revoked devices can no longer sync, but their history stays.
    revokedAt: integer("revoked_at", { mode: "timestamp_ms" }),
  },
  (table) => [index("devices_user").on(table.userId)],
);

export const ITEM_STATUSES = ["queued", "printed", "dismissed", "ignored"] as const;
export type ItemStatus = (typeof ITEM_STATUSES)[number];

export const items = sqliteTable(
  "items",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    deviceId: text("device_id")
      .notNull()
      .references(() => devices.id, { onDelete: "cascade" }),
    // The id in the daemon's own database. Commands are addressed with it.
    localId: integer("local_id").notNull(),
    source: text("source").notNull(),
    sender: text("sender").notNull().default(""),
    title: text("title").notNull(),
    detail: text("detail").notNull().default(""),
    priority: text("priority").notNull().default("normal"),
    due: text("due").notNull().default(""),
    status: text("status").$type<ItemStatus>().notNull(),
    engine: text("engine").notNull().default("none"),
    createdAt: integer("created_at", { mode: "timestamp_ms" }).notNull(),
    decidedAt: integer("decided_at", { mode: "timestamp_ms" }),
    // A custom design: base64 of the 312x216 grid. Plain notes have none.
    bitmap: text("bitmap"),
  },
  (table) => [
    uniqueIndex("items_device_local").on(table.deviceId, table.localId),
    index("items_device_created").on(table.deviceId, table.createdAt),
    index("items_status").on(table.status),
  ],
);

export const COMMAND_ACTIONS = ["print", "dismiss"] as const;
export type CommandAction = (typeof COMMAND_ACTIONS)[number];

/** A decision made on the web, waiting for the device to carry it out. */
export const commands = sqliteTable(
  "commands",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    deviceId: text("device_id")
      .notNull()
      .references(() => devices.id, { onDelete: "cascade" }),
    itemId: integer("item_id")
      .notNull()
      .references(() => items.id, { onDelete: "cascade" }),
    action: text("action").$type<CommandAction>().notNull(),
    createdAt: createdAt(),
    ackedAt: integer("acked_at", { mode: "timestamp_ms" }),
  },
  (table) => [index("commands_device_pending").on(table.deviceId, table.ackedAt)],
);

// --- Friends ----------------------------------------------------------------------------

/** People add each other with this code, so nobody's email is exposed or guessable. */
export const profiles = sqliteTable("profiles", {
  userId: text("user_id")
    .primaryKey()
    .references(() => user.id, { onDelete: "cascade" }),
  friendCode: text("friend_code").notNull().unique(),
});

export const friendships = sqliteTable(
  "friendships",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    requesterId: text("requester_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    addresseeId: text("addressee_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    status: text("status").$type<"pending" | "accepted">().notNull(),
    createdAt: createdAt(),
  },
  (table) => [
    uniqueIndex("friendships_pair").on(table.requesterId, table.addresseeId),
    index("friendships_addressee").on(table.addresseeId),
  ],
);

/** Off until granted: grantor lets grantee put notes in the grantor's queue. */
export const printPermissions = sqliteTable(
  "print_permissions",
  {
    grantorId: text("grantor_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    granteeId: text("grantee_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    createdAt: createdAt(),
  },
  (table) => [uniqueIndex("print_permissions_pair").on(table.grantorId, table.granteeId)],
);

export const printRequests = sqliteTable(
  "print_requests",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    senderId: text("sender_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    recipientId: text("recipient_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    title: text("title").notNull(),
    detail: text("detail").notNull().default(""),
    bitmap: text("bitmap"),
    createdAt: createdAt(),
    // The first device to ask gets it, so someone with two devices doesn't get it twice.
    claimedDeviceId: text("claimed_device_id"),
    deliveredAt: integer("delivered_at", { mode: "timestamp_ms" }),
  },
  (table) => [
    index("print_requests_recipient").on(table.recipientId, table.deliveredAt),
    index("print_requests_sender").on(table.senderId, table.createdAt),
  ],
);

export const deviceRelations = relations(devices, ({ many, one }) => ({
  owner: one(user, { fields: [devices.userId], references: [user.id] }),
  items: many(items),
}));

export const itemRelations = relations(items, ({ one }) => ({
  device: one(devices, { fields: [items.deviceId], references: [devices.id] }),
}));
