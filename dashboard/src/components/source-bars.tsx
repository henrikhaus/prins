import { formatNumber, sourceLabel } from "@/lib/format";

/** Ranked bars in one hue: the job is comparing sizes, not telling identities apart. */
export function SourceBars({ data }: { data: { source: string; value: number }[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing has come in yet.</p>;
  }
  const largest = Math.max(...data.map((row) => row.value));
  return (
    <ul className="flex flex-col gap-3">
      {data.map((row) => (
        <li
          key={row.source}
          className="grid grid-cols-[3.5rem_1fr_3rem] items-center gap-2 text-sm"
        >
          <span className="truncate text-muted-foreground">{sourceLabel(row.source)}</span>
          <span className="h-3 overflow-hidden" aria-hidden>
            <span
              className="block h-full rounded-r-[4px]"
              style={{ width: `${(row.value / largest) * 100}%`, background: "var(--viz-1)" }}
            />
          </span>
          <span className="text-right tabular-nums">{formatNumber(row.value)}</span>
        </li>
      ))}
    </ul>
  );
}
