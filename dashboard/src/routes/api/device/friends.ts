import { createFileRoute } from "@tanstack/react-router";

import { getFriends } from "@/server/friends.server";
import { authenticateDevice } from "@/server/sync.server";

export const Route = createFileRoute("/api/device/friends")({
  server: {
    handlers: {
      GET: ({ request }) => {
        const device = authenticateDevice(request.headers.get("authorization"));
        if (!device) return Response.json({ error: "Invalid device token" }, { status: 401 });
        const friends = getFriends(device.userId).friends.map((friend) => ({
          id: friend.id,
          name: friend.name,
          canSend: friend.canPrintToThem,
        }));
        return Response.json({ friends });
      },
    },
  },
});
