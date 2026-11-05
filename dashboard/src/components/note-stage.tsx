import { useRouter } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { ChevronLeft, ChevronRight, Printer, X } from "lucide-react";
import { useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

import type { QueueItem } from "@/components/note-paper";

import { HiddenNotes, isTyping } from "@/components/app-shell";
import { NotePaper, originOf } from "@/components/note-paper";
import { Button } from "@/components/ui/button";
import { timeAgo } from "@/lib/format";
import { decideFn } from "@/server/fns";

type Action = "print" | "dismiss";
type Grace = { item: QueueItem; action: Action; timer: ReturnType<typeof setTimeout> };

const UNDO_MS = 5000;
const UNFINISHED_KEY = "prins-unfinished-decision";
const SWIPE_DISTANCE = 130;

const GERUND: Record<Action, string> = { print: "Printing", dismiss: "Dismissing" };

/**
 * The desk: one note in front, the rest stacked behind. Swipe or press a key to decide. A decision
 * waits 5 seconds before it reaches the server, which is what makes it safe to undo. The stack's
 * motion is adapted from React Bits (Stack), MIT + Commons Clause, copyright (c) 2026 David Haz.
 */
export function useDesk(queue: QueueItem[]) {
  const router = useRouter();
  const decide = useServerFn(decideFn);
  const [hidden, setHidden] = useState<ReadonlySet<number>>(new Set());
  const [focusId, setFocusId] = useState<number | null>(null);
  const [leaving, setLeaving] = useState<{ item: QueueItem; action: Action; from: number } | null>(
    null,
  );
  const [toast, setToast] = useState<{ item: QueueItem; action: Action; key: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const grace = useRef<Grace | null>(null);
  const publishHidden = useContext(HiddenNotes);

  // The count in the navigation drops with the number on the desk, not 5 seconds later.
  useEffect(() => publishHidden(hidden), [hidden, publishHidden]);

  const unhide = useCallback((id: number) => {
    setHidden((set) => {
      const next = new Set(set);
      next.delete(id);
      return next;
    });
  }, []);

  const commit = useCallback(
    async (pending: Grace) => {
      clearTimeout(pending.timer);
      if (grace.current === pending) grace.current = null;
      setToast((current) => (current?.item.id === pending.item.id ? null : current));
      try {
        const { result } = await decide({
          data: { itemId: pending.item.id, action: pending.action },
        });
        if (result === "not_found") setError("That note was already decided on the device.");
        await router.invalidate();
      } catch {
        unhide(pending.item.id);
        setError("That didn't go through, so the note is back on your desk. Try again.");
      }
    },
    [decide, router, unhide],
  );

  const actionable = queue.filter((item) => !item.pendingAction && !hidden.has(item.id));
  const sent = queue.filter((item) => item.pendingAction);
  const currentIndex = Math.max(
    0,
    actionable.findIndex((item) => item.id === focusId),
  );
  const current = actionable[currentIndex] ?? null;

  const act = useCallback(
    (action: Action, from = 0) => {
      if (!current) return;
      if (grace.current) void commit(grace.current);
      setError(null);
      setLeaving({ item: current, action, from });
      setHidden((set) => new Set(set).add(current.id));
      setFocusId(actionable[currentIndex + 1]?.id ?? null);
      const pending: Grace = {
        item: current,
        action,
        timer: setTimeout(() => void commit(pending), UNDO_MS),
      };
      grace.current = pending;
      setToast({ item: current, action, key: Date.now() });
    },
    [actionable, commit, current, currentIndex],
  );

  const undo = useCallback(() => {
    const pending = grace.current;
    if (!pending) return;
    clearTimeout(pending.timer);
    grace.current = null;
    unhide(pending.item.id);
    setFocusId(pending.item.id);
    setToast(null);
    setLeaving(null);
  }, [unhide]);

  const step = useCallback(
    (by: number) => {
      if (actionable.length < 2) return;
      const next = (currentIndex + by + actionable.length) % actionable.length;
      setFocusId(actionable[next].id);
    },
    [actionable, currentIndex],
  );

  // Leaving the page, or the site, doesn't cancel a decision that was already made.
  useEffect(() => {
    // A closing tab can't finish a request, so remember the decision and finish it next visit.
    // If they never come back, the note is simply still in the queue, which is the safe way round.
    const onClose = () => {
      const pending = grace.current;
      if (!pending) return;
      clearTimeout(pending.timer);
      grace.current = null;
      try {
        localStorage.setItem(
          UNFINISHED_KEY,
          JSON.stringify({ itemId: pending.item.id, action: pending.action }),
        );
      } catch {
        // Private browsing: the note stays in the queue.
      }
    };
    try {
      const saved = localStorage.getItem(UNFINISHED_KEY);
      if (saved) {
        localStorage.removeItem(UNFINISHED_KEY);
        void decide({ data: JSON.parse(saved) }).then(() => router.invalidate());
      }
    } catch {
      // Nothing to finish.
    }
    window.addEventListener("pagehide", onClose);
    return () => {
      window.removeEventListener("pagehide", onClose);
      if (grace.current) void commit(grace.current);
    };
    // Must only run on unmount: commit is stable enough, and a re-run would flush too early.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || event.repeat) return;
      if (isTyping(event.target) || document.querySelector("[role=dialog],[role=menu]")) return;
      const key = event.key.toLowerCase();
      if (key === "p") act("print");
      else if (key === "d") act("dismiss");
      else if (key === "z") undo();
      else if (key === "j") step(1);
      else if (key === "k") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [act, step, undo]);

  return {
    actionable,
    sent,
    current,
    currentIndex,
    leaving,
    toast,
    error,
    act,
    undo,
    step,
    setFocusId,
    clearLeaving: () => setLeaving(null),
    clearError: () => setError(null),
  };
}

type Desk = ReturnType<typeof useDesk>;

function Stack({ desk }: { desk: Desk }) {
  const { actionable, currentIndex, leaving } = desk;
  const ordered = [...actionable.slice(currentIndex), ...actionable.slice(0, currentIndex)];
  const visible = ordered.slice(0, 3);
  const [drag, setDrag] = useState(0);
  const start = useRef<{ x: number; id: number } | null>(null);

  const onDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    start.current = { x: event.clientX, id: event.pointerId };
  };
  const onMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (start.current?.id === event.pointerId) setDrag(event.clientX - start.current.x);
  };
  const onUp = () => {
    const distance = drag;
    start.current = null;
    setDrag(0);
    if (distance > SWIPE_DISTANCE) desk.act("print", distance);
    else if (distance < -SWIPE_DISTANCE) desk.act("dismiss", distance);
  };

  const strength = Math.min(1, Math.abs(drag) / SWIPE_DISTANCE);

  return (
    <div className="note-feed relative mx-auto aspect-[312/216] w-full max-w-(--note-width)">
      {leaving?.action === "print" ? (
        <span key={`flash-${leaving.item.id}`} aria-hidden className="stage-flash" />
      ) : null}
      {[...visible].reverse().map((item) => {
        const depth = visible.indexOf(item);
        const isTop = depth === 0;
        return (
          <div
            key={item.id}
            className={`absolute inset-0 select-none ${
              isTop ? "cursor-grab touch-pan-y active:cursor-grabbing" : "pointer-events-none"
            }`}
            style={{
              zIndex: 10 - depth,
              filter: isTop ? undefined : `brightness(${1 - depth * 0.06})`,
              transform: isTop
                ? `translateX(${drag}px) rotate(${drag * 0.035}deg)`
                : `translateY(${depth * 4.5}%) scale(${1 - depth * 0.045})`,
              transition:
                drag === 0 ? "transform .45s cubic-bezier(.16,1,.3,1), filter .3s" : "none",
            }}
            onPointerDown={isTop ? onDown : undefined}
            onPointerMove={isTop ? onMove : undefined}
            onPointerUp={isTop ? onUp : undefined}
            onPointerCancel={
              isTop
                ? () => {
                    start.current = null;
                    setDrag(0);
                  }
                : undefined
            }
          >
            <NotePaper item={item} flat={!isTop} />
            {isTop && drag !== 0 ? (
              <span
                aria-hidden
                className="absolute top-[38%] rounded-md border-2 px-3 py-1 font-mono text-sm font-semibold tracking-widest uppercase"
                style={{
                  opacity: strength,
                  ...(drag > 0
                    ? { left: "6%", rotate: "-8deg", color: "#0f8f54", borderColor: "#0f8f54" }
                    : { right: "6%", rotate: "8deg", color: "#d63a24", borderColor: "#d63a24" }),
                  background: "#fffefb",
                }}
              >
                {drag > 0 ? "Print" : "Dismiss"}
              </span>
            ) : null}
          </div>
        );
      })}
      {leaving ? (
        <div
          key={`leaving-${leaving.item.id}`}
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            zIndex: 20,
            translate: `${leaving.from}px`,
            animation: `${leaving.action === "print" ? "note-print-out .6s cubic-bezier(.5,0,.75,0)" : "note-dismiss-out .4s cubic-bezier(.4,0,1,1)"} forwards`,
          }}
          onAnimationEnd={desk.clearLeaving}
        >
          <NotePaper item={leaving.item} />
        </div>
      ) : null}
    </div>
  );
}

export function NoteStage({ desk, offlineDevice }: { desk: Desk; offlineDevice: string | null }) {
  const { actionable, current, currentIndex } = desk;
  return (
    <div className="flex flex-col">
      <Stack desk={desk} />
      {current ? (
        <div className="relative z-30 mx-auto mt-10 flex w-full max-w-(--note-width) flex-col gap-2 short:mt-8">
          <div className="grid grid-cols-[1fr_1.5fr] gap-2.5">
            <Button
              size="lg"
              variant="onBrand"
              className="short:h-12"
              aria-keyshortcuts="d"
              onClick={() => desk.act("dismiss")}
            >
              <X aria-hidden />
              Dismiss
              <span className="kbd ml-1 hidden md:inline-flex">D</span>
            </Button>
            <Button
              size="lg"
              variant="hot"
              className="short:h-12"
              aria-keyshortcuts="p"
              onClick={() => desk.act("print")}
            >
              <Printer aria-hidden />
              Print
              <span className="kbd ml-1 hidden md:inline-flex">P</span>
            </Button>
          </div>
          <div className="flex min-h-8 items-center justify-between gap-3 text-[0.8125rem] text-white/85">
            <span className="min-w-0 text-pretty">
              {offlineDevice ? (
                <>{offlineDevice} is offline. It'll act on your decision when it's back.</>
              ) : (
                <>
                  Prints on {current.deviceName}.{" "}
                  <span className="max-md:hidden">Or drag the note right or left.</span>
                  <span className="md:hidden">Or swipe the note right or left.</span>
                </>
              )}
            </span>
            {actionable.length > 1 ? (
              <span className="flex shrink-0 items-center gap-0.5">
                <button
                  type="button"
                  aria-label="Previous note"
                  onClick={() => desk.step(-1)}
                  className="flex size-8 cursor-pointer items-center justify-center rounded-full hover:bg-white/15"
                >
                  <ChevronLeft className="size-4" aria-hidden />
                </button>
                <span className="font-mono text-xs tabular-nums">
                  {currentIndex + 1}/{actionable.length}
                </span>
                <button
                  type="button"
                  aria-label="Next note"
                  onClick={() => desk.step(1)}
                  className="flex size-8 cursor-pointer items-center justify-center rounded-full hover:bg-white/15"
                >
                  <ChevronRight className="size-4" aria-hidden />
                </button>
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** The queue as a list, so you can see what's coming and pull any note to the front. */
export function UpNext({ desk }: { desk: Desk }) {
  const { actionable, current, sent } = desk;
  const list = useRef<HTMLOListElement>(null);
  const tops = useRef(new Map<string, number>());
  const [highlight, setHighlight] = useState<{ top: number; height: number } | null>(null);

  // When a note leaves, the rows below glide up rather than jump.
  useLayoutEffect(() => {
    const rows = [...(list.current?.querySelectorAll<HTMLElement>("[data-row]") ?? [])];
    for (const row of rows) {
      const top = row.offsetTop;
      const was = tops.current.get(row.dataset.row ?? "");
      if (was !== undefined && was !== top) {
        row.animate([{ transform: `translateY(${was - top}px)` }, { transform: "none" }], {
          duration: 380,
          easing: "cubic-bezier(.16,1,.3,1)",
        });
      }
      tops.current.set(row.dataset.row ?? "", top);
    }
    const selected = list.current?.querySelector<HTMLElement>("[aria-current=true]")?.parentElement;
    setHighlight(selected ? { top: selected.offsetTop, height: selected.offsetHeight } : null);
  }, [actionable.length, current?.id]);

  return (
    <div className="flex flex-col gap-8">
      {actionable.length > 0 ? (
        <ol ref={list} className="relative flex flex-col">
          {highlight ? (
            <span
              aria-hidden
              className="absolute -inset-x-3 rounded-xl bg-accent transition-[top,height] duration-350 ease-[cubic-bezier(0.16,1,0.3,1)]"
              style={{ top: highlight.top, height: highlight.height }}
            />
          ) : null}
          {actionable.map((item, index) => {
            const selected = item.id === current?.id;
            return (
              <li key={item.id} data-row={item.id} className="relative">
                <button
                  type="button"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => desk.setFocusId(item.id)}
                  className={`-mx-3 flex w-[calc(100%+1.5rem)] cursor-pointer items-start gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                    selected ? "" : "hover:bg-accent/50"
                  }`}
                >
                  <span className="mt-[0.2rem] w-4 shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                    {index + 1}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{item.title}</span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground">
                      <span className="truncate">{originOf(item)}</span>
                      <span aria-hidden>·</span>
                      <span className="shrink-0" suppressHydrationWarning>
                        {timeAgo(item.createdAt)}
                      </span>
                    </span>
                  </span>
                  {item.priority === "high" ? (
                    <span className="mt-0.5 shrink-0 rounded-full bg-hot px-1.5 font-mono text-[0.6875rem] leading-[1.125rem] tracking-wide text-hot-foreground uppercase">
                      Urgent
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ol>
      ) : null}
      {sent.length > 0 ? (
        <div>
          <h3 className="eyebrow mb-2">Sent to the device</h3>
          <ul className="flex flex-col gap-2">
            {sent.map((item) => (
              <li key={item.id} className="flex items-baseline justify-between gap-3 text-sm">
                <span className="min-w-0 truncate text-muted-foreground">{item.title}</span>
                <span className="shrink-0 text-[0.8125rem] text-muted-foreground">
                  {item.pendingAction === "print" ? "Will print" : "Will dismiss"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Countdown({ action }: { action: Action }) {
  const [left, setLeft] = useState(UNDO_MS / 1000);
  useEffect(() => {
    const timer = setInterval(() => setLeft((value) => Math.max(1, value - 1)), 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <span className="font-medium tabular-nums">
      {GERUND[action]} in {left}s
    </span>
  );
}

export function DeskToast({ desk }: { desk: Desk }) {
  const { toast, error } = desk;
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(desk.clearError, 7000);
    return () => clearTimeout(timer);
  }, [error, desk.clearError]);

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-20 z-40 flex flex-col items-center gap-2 px-4 md:bottom-6"
    >
      {error ? (
        <p
          role="alert"
          className="pointer-events-auto rounded-2xl bg-destructive px-4 py-2.5 text-sm text-background shadow-lg"
        >
          {error}
        </p>
      ) : null}
      {toast ? (
        <div
          key={toast.key}
          className="rise-in pointer-events-auto relative flex max-w-full items-center gap-3 overflow-hidden rounded-full bg-foreground py-2 pr-2 pl-4 text-sm text-background shadow-2xl"
        >
          <span
            className="key-dot"
            style={{ background: toast.action === "print" ? "#35d48a" : "#ff6a4d" }}
            aria-hidden
          />
          <Countdown action={toast.action} />
          <span className="min-w-0 truncate opacity-70 max-sm:hidden">{toast.item.title}</span>
          <button
            type="button"
            onClick={desk.undo}
            className="flex h-8 shrink-0 cursor-pointer items-center gap-1.5 rounded-full bg-background/15 px-3 font-medium transition-colors hover:bg-background/25"
          >
            Undo
            <span className="kbd hidden md:inline-flex">Z</span>
          </button>
          <span
            aria-hidden
            className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-background/50"
            style={{ animation: `toast-drain ${UNDO_MS}ms linear forwards` }}
          />
        </div>
      ) : null}
    </div>
  );
}
