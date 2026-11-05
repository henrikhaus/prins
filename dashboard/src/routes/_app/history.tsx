import { createFileRoute, redirect } from "@tanstack/react-router";

import { historySchema } from "@/lib/schemas";

// History is part of Activity now. This keeps old links working.
export const Route = createFileRoute("/_app/history")({
  validateSearch: historySchema,
  beforeLoad: ({ search }) => {
    throw redirect({ to: "/activity", search });
  },
});
