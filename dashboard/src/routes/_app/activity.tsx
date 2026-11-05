import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";

import { PageHeader, Section } from "@/components/app-shell";
import { CountUp } from "@/components/count-up";
import { DecisionsChart, OUTCOME_TEXTURES } from "@/components/decisions-chart";
import { NotePaper } from "@/components/note-paper";
import { SourceBars } from "@/components/source-bars";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  STATUS_LABELS,
  formatDateTime,
  formatDayHeading,
  formatNumber,
  formatTime,
  sourceLabel,
} from "@/lib/format";
import { getHistoryFn, getOverviewFn } from "@/server/fns";

const searchSchema = z.object({
  status: z.enum(["all", "printed", "dismissed", "ignored"]).default("all").catch("all"),
  source: z.string().max(20).default("all").catch("all"),
  search: z.string().max(100).default("").catch(""),
  page: z.number().int().min(1).default(1).catch(1),
});

export const Route = createFileRoute("/_app/activity")({
  validateSearch: searchSchema,
  loaderDeps: ({ search }) => search,
  loader: async ({ deps }) => {
    const [overview, history] = await Promise.all([getOverviewFn(), getHistoryFn({ data: deps })]);
    return { overview: overview.overview, history };
  },
  head: () => ({ meta: [{ title: "Activity - Prins" }] }),
  component: ActivityPage,
});

const STATUS_FILTERS = [
  { value: "all", label: "All" },
  { value: "printed", label: "Printed" },
  { value: "dismissed", label: "Dismissed" },
  { value: "ignored", label: "Filtered" },
] as const;

function ActivityPage() {
  const { overview } = Route.useLoaderData();
  const { totals, keepRate } = overview;

  if (totals.received === 0) {
    return (
      <>
        <PageHeader title="Activity" />
        <div className="rise-in flex flex-1 flex-col items-center justify-center gap-5 py-16 text-center">
          <p className="font-dot text-[5.5rem] text-primary md:text-[8rem]">Quiet</p>
          <p className="max-w-sm text-pretty text-muted-foreground">
            Nothing has come in during the last {overview.days} days. Every message Prins sees shows
            up here, including the ones it filters out for you.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Activity" />

      <section className="on-brand rise-in flex flex-col gap-5 rounded-[2rem] bg-brand p-5 text-brand-foreground md:p-8">
        <div className="grid grid-cols-3 gap-x-4 gap-y-6 md:flex md:flex-wrap md:gap-x-14">
          <Figure value={totals.received} label="came in" />
          <Figure value={totals.printed} label="printed" />
          <Figure
            value={keepRate ?? 0}
            suffix="%"
            label="of suggestions kept"
            empty={keepRate === null}
          />
        </div>
        <FlowBar totals={totals} days={overview.days} />
      </section>

      <div className="grid gap-x-16 gap-y-12 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Log />
        <aside className="flex flex-col gap-12">
          <Section title="Per day">
            <DecisionsChart data={overview.chart} />
          </Section>
          <Section title="Where it came from">
            <SourceBars data={overview.sources} />
          </Section>
        </aside>
      </div>
    </>
  );
}

function Figure({
  value,
  label,
  suffix = "",
  empty = false,
}: {
  value: number;
  label: string;
  suffix?: string;
  empty?: boolean;
}) {
  return (
    <div>
      <p className="font-dot text-[2.75rem] text-hot md:text-[5rem]">
        {empty ? "-" : <CountUp value={value} />}
        {empty || !suffix ? null : (
          <span className="ml-0.5 align-top font-sans text-[0.4em] font-medium tracking-tight md:ml-1">
            {suffix}
          </span>
        )}
      </p>
      <p className="mt-2 text-[0.8125rem] text-white/85">{label}</p>
    </div>
  );
}

/** One bar for the whole period, so the share filtered out for you is the first thing you see. */
function FlowBar({
  totals,
  days,
}: {
  totals: { received: number; printed: number; dismissed: number; ignored: number; queued: number };
  days: number;
}) {
  const parts = [
    { key: "printed", label: "Printed", value: totals.printed },
    { key: "dismissed", label: "Dismissed", value: totals.dismissed },
    { key: "ignored", label: "Filtered by AI", value: totals.ignored },
    { key: "queued", label: "Waiting", value: totals.queued },
  ].filter((part) => part.value > 0);
  return (
    <figure className="flex flex-col gap-3">
      <div
        className="grow-x flex h-6 gap-0.5"
        role="img"
        aria-label={`Last ${days} days: ${parts
          .map((part) => `${part.value} ${part.label.toLowerCase()}`)
          .join(", ")}`}
      >
        {parts.map((part, index) => (
          <span
            key={part.key}
            className={`h-full ${OUTCOME_TEXTURES[part.key as keyof typeof OUTCOME_TEXTURES]}`}
            style={{
              flexGrow: part.value,
              flexBasis: 3,
              borderRadius: `${index === 0 ? 4 : 0}px ${index === parts.length - 1 ? 4 : 0}px ${index === parts.length - 1 ? 4 : 0}px ${index === 0 ? 4 : 0}px`,
            }}
          />
        ))}
      </div>
      <figcaption className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[0.8125rem]">
        {parts.map((part) => (
          <span key={part.key} className="flex items-center gap-2">
            <span
              className={`size-3 rounded-[2px] ${OUTCOME_TEXTURES[part.key as keyof typeof OUTCOME_TEXTURES]}`}
              aria-hidden
            />
            <span className="text-muted-foreground">{part.label}</span>
            <span className="font-mono text-xs tabular-nums">{formatNumber(part.value)}</span>
          </span>
        ))}
        <span className="text-muted-foreground md:ml-auto">Last {days} days</span>
      </figcaption>
    </figure>
  );
}

function Log() {
  const { history } = Route.useLoaderData();
  const { rows, total, pageSize, sources } = history;
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  const [text, setText] = useState(search.search);
  const [open, setOpen] = useState<(typeof rows)[number] | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const top = useRef<HTMLDivElement>(null);
  const filtered = search.status !== "all" || search.source !== "all" || Boolean(search.search);

  useEffect(() => () => clearTimeout(timer.current), []);

  const onSearch = (value: string) => {
    setText(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      void navigate({
        search: (previous) => ({ ...previous, search: value, page: 1 }),
        replace: true,
        resetScroll: false,
      });
    }, 250);
  };

  const clearAll = () => {
    setText("");
    void navigate({
      search: { status: "all", source: "all", search: "", page: 1 },
      resetScroll: false,
    });
  };

  const goTo = (page: number) => {
    void navigate({ search: (previous) => ({ ...previous, page }), resetScroll: false });
    top.current?.scrollIntoView({ block: "start" });
  };

  const days = new Map<string, typeof rows>();
  for (const row of rows) {
    const heading = formatDayHeading(row.createdAt);
    days.set(heading, [...(days.get(heading) ?? []), row]);
  }

  return (
    <div ref={top} className="min-w-0 scroll-mt-20">
      <Section title={`${formatNumber(total)} ${total === 1 ? "message" : "messages"}`}>
        <div className="mb-6 flex flex-col gap-3">
          <div className="flex gap-2">
            <div className="relative min-w-0 flex-1">
              <Search
                className="absolute top-1/2 left-3.5 size-3.5 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                value={text}
                onChange={(event) => onSearch(event.target.value)}
                type="search"
                placeholder="Search"
                aria-label="Search notes and senders"
                className="h-9 rounded-full pr-9 pl-9"
              />
              {text ? (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => onSearch("")}
                  className="absolute top-1/2 right-2 flex size-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <X className="size-3.5" aria-hidden />
                </button>
              ) : null}
            </div>
            <Select
              label="Filter by source"
              value={search.source}
              onChange={(value) =>
                void navigate({
                  search: (previous) => ({ ...previous, source: value, page: 1 }),
                  resetScroll: false,
                })
              }
              options={[
                { value: "all", label: "All sources" },
                ...sources.map((source) => ({ value: source, label: sourceLabel(source) })),
              ]}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <nav
              className="flex w-fit gap-0.5 rounded-full bg-muted p-1"
              aria-label="Filter by outcome"
            >
              {STATUS_FILTERS.map((filter) => (
                <Link
                  key={filter.value}
                  from={Route.fullPath}
                  search={(previous) => ({ ...previous, status: filter.value, page: 1 })}
                  resetScroll={false}
                  aria-current={search.status === filter.value ? "true" : undefined}
                  className={`shrink-0 rounded-full px-3 py-1 text-[0.8125rem] font-medium transition-colors ${
                    search.status === filter.value
                      ? "bg-background shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {filter.label}
                </Link>
              ))}
            </nav>
            {filtered ? (
              <button
                type="button"
                onClick={clearAll}
                className="cursor-pointer text-[0.8125rem] text-muted-foreground underline underline-offset-4 hover:text-foreground"
              >
                Clear filters
              </button>
            ) : null}
          </div>
        </div>

        {rows.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-14 text-center">
            <p className="text-muted-foreground">Nothing matches these filters.</p>
            {filtered ? (
              <Button variant="outline" size="sm" onClick={clearAll}>
                Clear filters
              </Button>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {[...days].map(([heading, group]) => (
              <div key={heading}>
                <h3 className="mb-1 text-[0.8125rem] font-medium">{heading}</h3>
                <ul className="flex flex-col divide-y">
                  {group.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        onClick={() => setOpen(row)}
                        className="-mx-2 grid w-[calc(100%+1rem)] cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-accent/70 md:grid-cols-[3rem_minmax(0,1fr)_auto]"
                      >
                        <span className="hidden font-mono text-xs text-muted-foreground tabular-nums md:block">
                          {formatTime(row.createdAt)}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">{row.title}</span>
                          <span className="block truncate text-[0.8125rem] text-muted-foreground">
                            <span className="md:hidden">{formatTime(row.createdAt)} · </span>
                            {sourceLabel(row.source)}
                            {row.sender ? ` - ${row.sender}` : ""}
                          </span>
                        </span>
                        <span className="flex items-center gap-2 text-[0.8125rem]">
                          <span
                            className={`size-3 rounded-[2px] ${OUTCOME_TEXTURES[row.status]}`}
                            aria-hidden
                          />
                          {STATUS_LABELS[row.status]}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {lastPage > 1 ? (
          <div className="mt-6 flex items-center justify-between text-sm">
            <Button
              variant="outline"
              size="sm"
              disabled={search.page <= 1}
              onClick={() => goTo(search.page - 1)}
            >
              Newer
            </Button>
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {search.page} / {lastPage}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={search.page >= lastPage}
              onClick={() => goTo(search.page + 1)}
            >
              Older
            </Button>
          </div>
        ) : null}
      </Section>

      <ItemDialog item={open} onClose={() => setOpen(null)} />
    </div>
  );
}

const WHY: Record<string, string> = {
  ignored: "AI decided this didn't need you, so it never reached your desk.",
  dismissed: "You dismissed this note.",
  printed: "You printed this note.",
};

function ItemDialog({
  item,
  onClose,
}: {
  item: {
    source: string;
    sender: string;
    title: string;
    status: keyof typeof STATUS_LABELS;
    createdAt: Date;
    decidedAt: Date | null;
  } | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={item !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:!max-w-md">
        {item ? (
          <>
            <DialogHeader>
              <DialogTitle>{STATUS_LABELS[item.status]}</DialogTitle>
              <DialogDescription>{WHY[item.status]}</DialogDescription>
            </DialogHeader>
            <NotePaper
              className="mx-auto w-full"
              item={{ ...item, detail: "", priority: "normal", due: "", bitmap: null }}
            />
            <dl className="flex flex-col text-sm">
              {[
                ["From", `${sourceLabel(item.source)}${item.sender ? ` - ${item.sender}` : ""}`],
                ["Received", formatDateTime(item.createdAt)],
                ...(item.decidedAt ? [["Decided", formatDateTime(item.decidedAt)]] : []),
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between gap-4 border-t py-2">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="min-w-0 truncate text-right">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="-mt-2 text-xs text-pretty text-muted-foreground">
              The original message stays on your Mac. Only this short note reaches the dashboard.
            </p>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
