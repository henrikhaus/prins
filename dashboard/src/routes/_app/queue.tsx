import { createFileRoute } from "@tanstack/react-router";

import { PageHeader, Panel } from "@/components/app-shell";
import { NoteCard } from "@/components/note-card";
import { getQueueFn } from "@/server/fns";

export const Route = createFileRoute("/_app/queue")({
  loader: () => getQueueFn(),
  head: () => ({ meta: [{ title: "Queue - Prins" }] }),
  component: QueuePage,
});

function QueuePage() {
  const { queue, devices } = Route.useLoaderData();
  const online = new Map(devices.map((device) => [device.name, device.online]));

  return (
    <>
      <PageHeader
        title="Queue"
        description={
          queue.length === 1
            ? "1 note is waiting for a decision."
            : `${queue.length} notes are waiting for a decision.`
        }
      />
      {queue.length === 0 ? (
        <Panel>
          <p className="text-sm text-muted-foreground">
            All clear. New notes show up here and on the device.
          </p>
        </Panel>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {queue.map((item) => (
            <NoteCard key={item.id} item={item} online={online.get(item.deviceName) ?? false} />
          ))}
        </div>
      )}
    </>
  );
}
