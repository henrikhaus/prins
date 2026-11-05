import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowRight, Check, Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";

import type { QueueItem } from "@/components/note-paper";

import { AddDeviceDialog } from "@/components/add-device";
import { CountUp } from "@/components/count-up";
import { DeskToast, NoteStage, UpNext, useDesk } from "@/components/note-stage";
import { Button } from "@/components/ui/button";
import { getOverviewFn } from "@/server/fns";

export const Route = createFileRoute("/_app/")({
  loader: () => getOverviewFn(),
  head: () => ({ meta: [{ title: "Desk - Prins" }] }),
  component: DeskPage,
});

// Sized by the viewport as well as the column, so Print is on screen on a laptop.
const NOTE_WIDTH = { "--note-width": "max(19rem, min(34rem, calc((100svh - 25.5rem) * 1.444)))" };

/** The solid brown stage everything important happens on. */
function Stage({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`on-brand rise-in relative isolate overflow-hidden rounded-[2rem] bg-brand p-5 text-brand-foreground md:p-8 ${className}`}
    >
      {children}
    </section>
  );
}

function DeskPage() {
  const { overview, queue, devices } = Route.useLoaderData();
  const desk = useDesk(queue as QueueItem[]);

  const notConnected = devices.filter((device) => !device.lastSeenAt && !device.isDemo);
  if (devices.length === 0 || (notConnected.length === devices.length && queue.length === 0)) {
    return <Welcome device={notConnected[0]} />;
  }

  const count = desk.actionable.length;
  const offline = desk.current
    ? devices.find((device) => device.name === desk.current?.deviceName && !device.online)
    : undefined;
  const summary = (
    <section className="rise-in border-t pt-4" style={{ "--i": 3 } as CSSProperties}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="eyebrow">Last {overview.days} days</h2>
        <Link
          to="/activity"
          viewTransition
          className="group flex items-center gap-1 text-[0.8125rem] text-muted-foreground transition-colors hover:text-foreground"
        >
          All activity
          <ArrowRight
            className="size-3 transition-transform group-hover:translate-x-0.5"
            aria-hidden
          />
        </Link>
      </div>
      <dl className="grid grid-cols-3 gap-3">
        <Tally label="Came in" value={overview.totals.received} />
        <Tally label="Filtered" value={overview.totals.ignored} />
        <Tally label="Printed" value={overview.totals.printed} />
      </dl>
    </section>
  );

  if (count === 0 && !desk.leaving && desk.sent.length === 0) {
    return (
      <div className="grid flex-1 content-start gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <Stage className="flex min-h-[26rem] flex-col items-center justify-center gap-5 text-center lg:min-h-[calc(100svh-7.5rem)]">
          <h1 className="font-dot text-[5.5rem] text-hot md:text-[9rem]">Clear</h1>
          <p className="max-w-sm text-[0.9375rem] text-pretty text-white/85">
            Nothing needs you right now. New notes show up here and on your device.
          </p>
        </Stage>
        <aside className="lg:pt-3">{summary}</aside>
        <DeskToast desk={desk} />
      </div>
    );
  }

  return (
    <div
      className="grid flex-1 content-start gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_21rem]"
      style={NOTE_WIDTH as CSSProperties}
    >
      <Stage className="flex flex-col justify-center gap-5 short:gap-3 lg:min-h-[calc(100svh-7.5rem)]">
        <header className="mx-auto flex w-full max-w-(--note-width) items-end gap-4">
          <CountUp
            value={count}
            className="font-dot text-[5rem] text-[#fff3df] short:text-[4rem] md:text-[6.5rem]"
          />
          <h1 className="pb-1 text-xl leading-tight font-semibold tracking-[-0.02em] text-white md:text-2xl">
            {count === 1 ? "note is" : "notes are"}
            <br />
            waiting for you
          </h1>
        </header>
        <NoteStage desk={desk} offlineDevice={offline?.name ?? null} />
      </Stage>

      <aside className="flex flex-col gap-10 lg:pt-3">
        <section className="rise-in">
          <h2 className="eyebrow mb-3">Your queue</h2>
          <UpNext desk={desk} />
        </section>
        {summary}
      </aside>

      <DeskToast desk={desk} />
    </div>
  );
}

function Tally({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="mt-1 text-[0.8125rem] text-muted-foreground">{label}</dt>
      <dd>
        <CountUp value={value} className="text-2xl font-medium tracking-[-0.03em]" />
      </dd>
    </div>
  );
}

const STEPS = [
  ["Add your device", "Give it a name and you'll get a one-time token."],
  ["Connect Prins on your Mac", "Paste two lines into its .env file, then restart it."],
  ["Wait for your first note", "Your desk fills up as soon as a message comes in."],
] as const;

function Welcome({ device }: { device?: { id: string; name: string } }) {
  const [adding, setAdding] = useState(false);
  const done = device ? 1 : 0;
  return (
    <div className="grid flex-1 content-start gap-x-12 gap-y-8 lg:grid-cols-2 lg:items-stretch">
      <Stage className="flex min-h-[20rem] flex-col justify-end gap-4 lg:min-h-[calc(100svh-7.5rem)]">
        <p className="font-dot text-[4.5rem] text-hot md:text-[7rem]">
          {device ? "Almost" : "Hello"}
        </p>
        <h1 className="max-w-md text-2xl leading-tight font-medium tracking-[-0.02em] text-balance md:text-3xl">
          {device
            ? `${device.name} hasn't connected yet.`
            : "Three steps to your first sticky note."}
        </h1>
      </Stage>
      <div className="flex flex-col justify-center gap-8">
        <ol className="rise-in flex flex-col border-t">
          {STEPS.map(([title, detail], index) => (
            <li key={title} className="flex gap-4 border-b py-4">
              <span
                className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-xs ${
                  index === done
                    ? "bg-primary text-primary-foreground"
                    : "border text-muted-foreground"
                }`}
              >
                {index < done ? <Check className="size-3.5" aria-label="Done" /> : index + 1}
              </span>
              <span className={index < done ? "text-muted-foreground" : ""}>
                <span className="block font-medium">{title}</span>
                <span className="mt-0.5 block text-sm text-muted-foreground">{detail}</span>
              </span>
            </li>
          ))}
        </ol>
        <div className="rise-in flex flex-col items-start gap-3">
          <Button size="lg" onClick={() => setAdding(true)}>
            {device ? <RefreshCw aria-hidden /> : <Plus aria-hidden />}
            {device ? "Get a new token" : "Add your device"}
          </Button>
          {device ? (
            <p className="max-w-sm text-[0.8125rem] text-pretty text-muted-foreground">
              Already pasted it? This page updates by itself once it connects. A new token replaces
              the old one.
            </p>
          ) : null}
        </div>
      </div>
      <AddDeviceDialog open={adding} onOpenChange={setAdding} existing={device} />
    </div>
  );
}
