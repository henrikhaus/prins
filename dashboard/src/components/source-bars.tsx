import type { CSSProperties } from "react";

import { formatNumber, sourceLabel } from "@/lib/format";

/** Ranked bars in one hue: the job is comparing sizes, not telling identities apart. */
export function SourceBars({ data }: { data: { source: string; value: number }[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing has come in yet.</p>;
  }
  const largest = Math.max(...data.map((row) => row.value));
  return (
    <ul className="flex flex-col gap-4">
      {data.map((row, index) => (
        <li key={row.source} className="flex flex-col gap-1.5 text-sm">
          <span className="flex items-baseline justify-between gap-2">
            <span>{sourceLabel(row.source)}</span>
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {formatNumber(row.value)}
            </span>
          </span>
          <span className="h-1.5 overflow-hidden" aria-hidden>
            <span
              className="grow-x block h-full rounded-r-[4px] bg-primary"
              style={{ width: `${(row.value / largest) * 100}%`, "--i": index } as CSSProperties}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}
