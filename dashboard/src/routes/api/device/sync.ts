import { createFileRoute } from "@tanstack/react-router";

import { syncRequestSchema } from "@/lib/schemas";
import { authenticateDevice, syncDevice } from "@/server/sync.server";

const MAX_BODY_BYTES = 1024 * 1024;

export const Route = createFileRoute("/api/device/sync")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const device = authenticateDevice(request.headers.get("authorization"));
        if (!device) return Response.json({ error: "Invalid device token" }, { status: 401 });

        const text = await request.text();
        if (text.length > MAX_BODY_BYTES) {
          return Response.json({ error: "Body too large" }, { status: 413 });
        }

        let body: unknown;
        try {
          body = JSON.parse(text);
        } catch {
          return Response.json({ error: "Body is not JSON" }, { status: 400 });
        }
        const parsed = syncRequestSchema.safeParse(body);
        if (!parsed.success) {
          return Response.json({ error: "Invalid sync payload" }, { status: 400 });
        }
        return Response.json(syncDevice(device.id, parsed.data));
      },
    },
  },
});
