import { createFileRoute, redirect } from "@tanstack/react-router";

// The queue is the desk now. This keeps old links working.
export const Route = createFileRoute("/_app/queue")({
  beforeLoad: () => {
    throw redirect({ to: "/" });
  },
});
