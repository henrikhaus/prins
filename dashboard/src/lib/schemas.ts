import { z } from "zod";

/** 312x216 at one bit per pixel is 8424 bytes, which is 11232 characters of base64. */
export const NOTE_WIDTH = 312;
export const NOTE_HEIGHT = 216;
export const bitmapSchema = z
  .string()
  .length(11232)
  .regex(/^[A-Za-z0-9+/]+={0,2}$/);

/** What the daemon sends. It never includes the raw message text, only the short note. */
export const syncRequestSchema = z.object({
  status: z.object({
    deviceKind: z.string().max(20),
    printer: z.string().max(20),
    handyInstalled: z.boolean(),
    slack: z.boolean(),
    email: z.boolean(),
    mode: z.string().max(20),
    queue: z.number().int().min(0),
    version: z.string().max(20),
  }),
  items: z
    .array(
      z.object({
        localId: z.number().int().positive(),
        source: z.string().min(1).max(20),
        sender: z.string().max(120),
        title: z.string().max(300),
        detail: z.string().max(500),
        priority: z.enum(["high", "normal", "low"]),
        due: z.string().max(80),
        status: z.enum(["queued", "printed", "dismissed", "ignored"]),
        engine: z.string().max(20),
        createdAt: z.number().int().positive(),
        decidedAt: z.number().int().positive().nullable(),
        bitmap: bitmapSchema.nullish(),
      }),
    )
    .max(50),
  ackedCommands: z.array(z.number().int().positive()).max(200),
  ackedRequests: z.array(z.number().int().positive()).max(200).default([]),
});

export type SyncRequest = z.infer<typeof syncRequestSchema>;

export const decideSchema = z.object({
  itemId: z.number().int().positive(),
  action: z.enum(["print", "dismiss"]),
});

export const historySchema = z.object({
  status: z.enum(["all", "printed", "dismissed", "ignored"]).catch("all"),
  source: z.string().max(20).catch("all"),
  search: z.string().max(100).catch(""),
  page: z.number().int().min(1).catch(1),
});

export type HistorySearch = z.infer<typeof historySchema>;

export const createDeviceSchema = z.object({
  name: z.string().trim().min(1, "Give it a name").max(60),
});

export const revokeDeviceSchema = z.object({ deviceId: z.uuid() });

export const addFriendSchema = z.object({ code: z.string().trim().min(4).max(30) });
export const friendshipIdSchema = z.object({ friendshipId: z.number().int().positive() });
export const respondFriendSchema = friendshipIdSchema.extend({ accept: z.boolean() });
export const friendIdSchema = z.object({ friendId: z.string().min(1).max(100) });
export const setPermissionSchema = friendIdSchema.extend({ allowed: z.boolean() });

const noteFields = {
  title: z.string().trim().min(1, "Write something").max(120),
  detail: z.string().trim().max(200).default(""),
  bitmap: bitmapSchema.nullish(),
};
export const sendNoteSchema = friendIdSchema.extend(noteFields);
export const devicePrintRequestSchema = z.object({
  to: z.string().trim().min(1).max(100),
  ...noteFields,
});
