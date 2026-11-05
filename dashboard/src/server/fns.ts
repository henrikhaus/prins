import { createMiddleware, createServerFn } from "@tanstack/react-start";
import { getRequestHeaders } from "@tanstack/react-start/server";

import {
  addFriendSchema,
  createDeviceSchema,
  decideSchema,
  friendIdSchema,
  historySchema,
  respondFriendSchema,
  revokeDeviceSchema,
  sendNoteSchema,
  setPermissionSchema,
} from "@/lib/schemas";

import { auth, signUpAllowed } from "./auth.server";
import {
  addFriend,
  getFriends,
  removeFriend,
  respondToFriend,
  sendNote,
  setPermission,
} from "./friends.server";
import {
  createDevice,
  decideItem,
  getDevices,
  getHistory,
  getOverview,
  getQueue,
  revokeDevice,
} from "./queries.server";

const requireUser = createMiddleware({ type: "function" }).server(async ({ next }) => {
  const session = await auth.api.getSession({ headers: getRequestHeaders() });
  if (!session) throw new Error("Unauthorized");
  return next({ context: { userId: session.user.id } });
});

export const getSessionFn = createServerFn({ method: "GET" }).handler(async () => {
  const session = await auth.api.getSession({ headers: getRequestHeaders() });
  return session ? { name: session.user.name, email: session.user.email } : null;
});

export const getAuthConfigFn = createServerFn({ method: "GET" }).handler(() => ({
  signUpAllowed: signUpAllowed(),
}));

export const getOverviewFn = createServerFn({ method: "GET" })
  .middleware([requireUser])
  .handler(({ context }) => ({
    overview: getOverview(context.userId),
    queue: getQueue(context.userId),
    devices: getDevices(context.userId),
  }));

export const getQueueFn = createServerFn({ method: "GET" })
  .middleware([requireUser])
  .handler(({ context }) => ({
    queue: getQueue(context.userId),
    devices: getDevices(context.userId),
  }));

export const decideFn = createServerFn({ method: "POST" })
  .middleware([requireUser])
  .validator(decideSchema)
  .handler(({ context, data }) => ({
    result: decideItem(context.userId, data.itemId, data.action),
  }));

export const getHistoryFn = createServerFn({ method: "GET" })
  .middleware([requireUser])
  .validator(historySchema)
  .handler(({ context, data }) => getHistory(context.userId, data));

export const getDevicesFn = createServerFn({ method: "GET" })
  .middleware([requireUser])
  .handler(({ context }) => getDevices(context.userId));

export const createDeviceFn = createServerFn({ method: "POST" })
  .middleware([requireUser])
  .validator(createDeviceSchema)
  .handler(({ context, data }) => createDevice(context.userId, data.name));

export const revokeDeviceFn = createServerFn({ method: "POST" })
  .middleware([requireUser])
  .validator(revokeDeviceSchema)
  .handler(({ context, data }) => {
    revokeDevice(context.userId, data.deviceId);
    return { ok: true };
  });

export const getFriendsFn = createServerFn({ method: "GET" })
  .middleware([requireUser])
  .handler(({ context }) => getFriends(context.userId));

export const addFriendFn = createServerFn({ method: "POST" })
  .middleware([requireUser])
  .validator(addFriendSchema)
  .handler(({ context, data }) => addFriend(context.userId, data.code));

export const respondFriendFn = createServerFn({ method: "POST" })
  .middleware([requireUser])
  .validator(respondFriendSchema)
  .handler(({ context, data }) => {
    respondToFriend(context.userId, data.friendshipId, data.accept);
    return { ok: true };
  });

export const removeFriendFn = createServerFn({ method: "POST" })
  .middleware([requireUser])
  .validator(friendIdSchema)
  .handler(({ context, data }) => {
    removeFriend(context.userId, data.friendId);
    return { ok: true };
  });

export const setPermissionFn = createServerFn({ method: "POST" })
  .middleware([requireUser])
  .validator(setPermissionSchema)
  .handler(({ context, data }) => {
    setPermission(context.userId, data.friendId, data.allowed);
    return { ok: true };
  });

export const sendNoteFn = createServerFn({ method: "POST" })
  .middleware([requireUser])
  .validator(sendNoteSchema)
  .handler(({ context, data }) => sendNote(context.userId, data.friendId, data));
