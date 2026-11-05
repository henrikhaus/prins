import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowRight, FlaskConical } from "lucide-react";

import { PageHeader, Panel } from "@/components/app-shell";
import { DecisionsChart } from "@/components/decisions-chart";
import { OnlineBadge, StatusList } from "@/components/device-status";
import { NoteCard } from "@/components/note-card";
import { SourceBars } from "@/components/source-bars";
import { formatNumber } from "@/lib/format";
import { getOverviewFn } from "@/server/fns";

export const Route = createFileRoute("/_app/")({
  loader: () => getOverviewFn(),
  head: () => ({ meta: [{ title: "Overview - Prins" }] }),
  component: OverviewPage,
});

function OverviewPage() {
  const { overview, queue, devices } = Route.useLoaderData();
  const { totals, keepRate } = overview;
  const next = queue[0];
  const nextDevice = next ? devices.find((device) => device.name === next.deviceName) : undefined;

  if (devices.length === 0) return <Welcome />;

  return (
    <>
      <PageHeader title="Overview" description={`The last ${overview.days} days`} />

      {overview.hasDemoDevice ? (
        <p className="flex items-center gap-2 rounded-lg border bg-muted px-3 py-2 text-sm">
          <FlaskConical className="size-4 shrink-0" aria-hidden />
          Sample data. These numbers are made up to show how the dashboard works.
        </p>
      ) : null}

      <section className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-5xl font-semibold tracking-tight tabular-nums md:text-6xl">
          {formatNumber(totals.received)}
        </span>
        <span className="text-lg text-muted-foreground">messages came in.</span>
        <span className="text-5xl font-semibold tracking-tight tabular-nums md:text-6xl">
          {formatNumber(totals.printed)}
        </span>
        <span className="text-lg text-muted-foreground">
          {totals.printed === 1 ? "became a note." : "became notes."}
        </span>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Filtered by the model" value={formatNumber(totals.ignored)} />
        <Stat label="You dismissed" value={formatNumber(totals.dismissed)} />
        <Stat label="Waiting in the queue" value={formatNumber(totals.queued)} />
        <Stat label="Suggestions you kept" value={keepRate === null ? "-" : `${keepRate}%`} />
      </section>

      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <Panel title="What happened to each message">
          <DecisionsChart data={overview.chart} />
        </Panel>

        <Panel>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-medium">Next up</h2>
            <Link
              to="/queue"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Queue ({formatNumber(queue.length)})
              <ArrowRight className="size-3" aria-hidden />
            </Link>
          </div>
          {next ? (
            <NoteCard item={next} online={nextDevice?.online ?? false} />
          ) : (
            <p className="text-sm text-muted-foreground">
              All clear. New notes show up here and on the device.
            </p>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Where messages come from">
          <SourceBars data={overview.sources} />
        </Panel>
        <Panel>
          <div className="mb-4 flex items-center justify-between gap-2">
            <h2 className="truncate text-sm font-medium">{devices[0].name}</h2>
            <OnlineBadge device={devices[0]} />
          </div>
          <StatusList device={devices[0]} />
        </Panel>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Welcome() {
  return (
    <>
      <PageHeader title="Welcome to Prins" />
      <Panel>
        <p className="text-sm">Connect your device to see its queue and history here.</p>
        <Link
          to="/devices"
          className="mt-3 inline-flex items-center gap-1 text-sm font-medium underline underline-offset-4"
        >
          Add your device
          <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      </Panel>
    </>
  );
}
