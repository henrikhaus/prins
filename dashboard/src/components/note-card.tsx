import { useServerFn } from "@tanstack/react-start";
import { useRouter } from "@tanstack/react-router";
import { Clock, Printer, X } from "lucide-react";
import { useState } from "react";

import { NoteBitmap } from "@/components/note-bitmap";
import { Button } from "@/components/ui/button";
import { formatDateTime, sourceLabel } from "@/lib/format";
import { decideFn } from "@/server/fns";

export type QueueItem = {
  id: number;
  source: string;
  sender: string;
  title: string;
  detail: string;
  priority: string;
  due: string;
  createdAt: Date;
  deviceName: string;
  pendingAction: "print" | "dismiss" | null;
  bitmap: string | null;
};

/** Drawn like the printed note: black on white paper, in dark mode too. */
export function NoteCard({ item, online }: { item: QueueItem; online: boolean }) {
  const router = useRouter();
  const decide = useServerFn(decideFn);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const act = async (action: "print" | "dismiss") => {
    setBusy(true);
    setError(null);
    try {
      const { result } = await decide({ data: { itemId: item.id, action } });
      if (result === "not_found") setError("This note was already decided on the device.");
      await router.invalidate();
    } catch {
      setError("That didn't go through. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const origin = sourceLabel(item.source).toUpperCase() + (item.sender ? ` - ${item.sender}` : "");

  return (
    <div className="flex flex-col gap-3">
      {item.bitmap ? (
        <figure className="flex flex-col gap-1.5">
          <NoteBitmap
            bitmap={item.bitmap}
            label={item.title}
            className="note-paper rounded-[3px]"
          />
          <figcaption className="truncate text-xs text-muted-foreground">{origin}</figcaption>
        </figure>
      ) : (
        <article className="note-paper rounded-[3px] p-4">
          <p className="truncate text-xs tracking-wide">{origin}</p>
          <hr className="my-2 border-t-2 border-black" />
          <h3 className="text-lg leading-snug font-bold text-balance">{item.title}</h3>
          {item.detail ? <p className="mt-2 text-sm leading-relaxed">{item.detail}</p> : null}
          <p className="mt-3 text-xs">
            {item.due ? `Due: ${item.due}` : formatDateTime(item.createdAt)}
            {item.priority === "high" ? " · Urgent" : ""}
          </p>
        </article>
      )}

      {item.pendingAction ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Clock className="size-4 shrink-0" aria-hidden />
          {online
            ? `Sending "${item.pendingAction}" to ${item.deviceName}...`
            : `Will ${item.pendingAction} when ${item.deviceName} is back online.`}
        </p>
      ) : (
        <div className="flex gap-2">
          <Button className="flex-1" disabled={busy} onClick={() => act("print")}>
            <Printer aria-hidden />
            Print
          </Button>
          <Button
            className="flex-1"
            variant="outline"
            disabled={busy}
            onClick={() => act("dismiss")}
          >
            <X aria-hidden />
            Dismiss
          </Button>
        </div>
      )}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
