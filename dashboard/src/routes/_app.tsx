import { Outlet, createFileRoute, redirect, useRouter } from "@tanstack/react-router";
import { useEffect } from "react";

import { AppShell } from "@/components/app-shell";
import { getSessionFn } from "@/server/fns";

const REFRESH_MS = 5000;

export const Route = createFileRoute("/_app")({
  beforeLoad: async () => {
    const session = await getSessionFn();
    if (!session) throw redirect({ to: "/login" });
    return { session };
  },
  component: AppLayout,
});

function AppLayout() {
  const { session } = Route.useRouteContext();
  const router = useRouter();

  // Keeps the queue and device status current while the tab is visible.
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) void router.invalidate();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [router]);

  return (
    <AppShell email={session.email}>
      <Outlet />
    </AppShell>
  );
}
