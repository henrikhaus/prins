import { createFileRoute } from "@tanstack/react-router";

import { devicePrintRequestSchema } from "@/lib/schemas";
import { sendNoteByName } from "@/server/friends.server";
import { authenticateDevice } from "@/server/sync.server";

const MAX_BODY_BYTES = 64 * 1024;

/** Used by the MCP server's send_to_friend. */
export const Route = createFileRoute("/api/device/print-requests")({
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
        const parsed = devicePrintRequestSchema.safeParse(body);
        if (!parsed.success) {
          return Response.json(
            { error: "A note needs a friend, a title, and a 312x216 bitmap if it has a design." },
            { status: 400 },
          );
        }
        const result = sendNoteByName(device.userId, parsed.data.to, parsed.data);
        if (!result.ok) return Response.json({ error: result.error }, { status: result.status });
        return Response.json({ message: result.message });
      },
    },
  },
});
