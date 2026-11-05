import { Outlet, createFileRoute, redirect, useRouter } from "@tanstack/react-router";
import { useEffect } from "react";

import { AppShell } from "@/components/app-shell";
import { getDevicesFn, getFriendsFn, getQueueFn, getSessionFn } from "@/server/fns";

const REFRESH_MS = 5000;

export const Route = createFileRoute("/_app")({
  beforeLoad: async () => {
    const session = await getSessionFn();
    if (!session) throw redirect({ to: "/login" });
    return { session };
  },
  // What every page's frame needs: the device in the top bar and the counts in the navigation.
  loader: async () => {
    const [{ queue }, devices, friends] = await Promise.all([
      getQueueFn(),
      getDevicesFn(),
      getFriendsFn(),
    ]);
    return {
      devices,
      waitingIds: queue.filter((item) => !item.pendingAction).map((item) => item.id),
      requests: friends.incoming.length,
    };
  },
  component: AppLayout,
});

function AppLayout() {
  const { session } = Route.useRouteContext();
  const { devices, waitingIds, requests } = Route.useLoaderData();
  const router = useRouter();

  // Keeps the queue and device status current while the tab is visible.
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) void router.invalidate();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [router]);

  return (
    <AppShell
      email={session.email}
      name={session.name}
      devices={devices}
      waitingIds={waitingIds}
      requests={requests}
    >
      <Outlet />
    </AppShell>
  );
}
