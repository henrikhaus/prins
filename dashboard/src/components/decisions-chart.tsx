import { formatDay, formatNumber, niceCeiling } from "@/lib/format";

type Day = { day: string; printed: number; dismissed: number; ignored: number };

// Stacked from the baseline up. Colour follows the outcome, never its size.
const SERIES = [
  { key: "ignored", label: "Filtered by the model", color: "var(--viz-3)" },
  { key: "dismissed", label: "Dismissed", color: "var(--viz-2)" },
  { key: "printed", label: "Printed", color: "var(--viz-1)" },
] as const;

const PLOT_HEIGHT = 180;

export function DecisionsChart({ data }: { data: Day[] }) {
  const totals = data.map((day) => day.printed + day.dismissed + day.ignored);
  const top = niceCeiling(Math.max(...totals, 1));
  const ticks = [top, top / 2, 0];

  return (
    <figure className="flex flex-col gap-4">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {SERIES.map((series) => (
          <li key={series.key} className="flex items-center gap-1.5">
            <span
              className="size-2.5 rounded-[2px]"
              style={{ background: series.color }}
              aria-hidden
            />
            {series.label}
          </li>
        ))}
      </ul>

      <div className="grid grid-cols-[auto_1fr] gap-x-2">
        <div
          className="relative w-7 text-right text-xs text-muted-foreground"
          style={{ height: PLOT_HEIGHT }}
        >
          {ticks.map((tick) => (
            <span
              key={tick}
              className="absolute right-0 -translate-y-1/2 tabular-nums"
              style={{ top: PLOT_HEIGHT - (tick / top) * PLOT_HEIGHT }}
            >
              {formatNumber(tick)}
            </span>
          ))}
        </div>

        <div className="relative" style={{ height: PLOT_HEIGHT }}>
          {ticks.map((tick) => (
            <div
              key={tick}
              className="absolute inset-x-0 border-t border-border"
              style={{ top: PLOT_HEIGHT - (tick / top) * PLOT_HEIGHT }}
              aria-hidden
            />
          ))}
          <div className="absolute inset-0 flex">
            {data.map((day, index) => (
              <Column key={day.day} day={day} top={top} index={index} count={data.length} />
            ))}
          </div>
        </div>

        <div />
        <div className="mt-1.5 flex text-xs text-muted-foreground">
          {data.map((day, index) => (
            <span key={day.day} className="relative h-4 flex-1 text-center">
              {index === 0 || index === data.length - 1 || index === Math.floor(data.length / 2) ? (
                <span className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap">
                  {formatDay(day.day)}
                </span>
              ) : null}
            </span>
          ))}
        </div>
      </div>

      <details className="text-sm">
        <summary className="cursor-pointer text-xs text-muted-foreground">Show as a table</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-1 pr-4 font-normal">Day</th>
                {SERIES.map((series) => (
                  <th key={series.key} className="py-1 pr-4 text-right font-normal">
                    {series.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((day) => (
                <tr key={day.day} className="border-t">
                  <td className="py-1 pr-4 whitespace-nowrap">{formatDay(day.day)}</td>
                  {SERIES.map((series) => (
                    <td key={series.key} className="py-1 pr-4 text-right tabular-nums">
                      {formatNumber(day[series.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function Column({
  day,
  top,
  index,
  count,
}: {
  day: Day;
  top: number;
  index: number;
  count: number;
}) {
  const total = day.printed + day.dismissed + day.ignored;
  const visible = SERIES.filter((series) => day[series.key] > 0);
  // Keep the tooltip on the page at both ends of the chart.
  const align = index < 3 ? "left-0" : index >= count - 3 ? "right-0" : "left-1/2 -translate-x-1/2";
  const summary = `${formatDay(day.day)}: ${SERIES.map(
    (series) => `${day[series.key]} ${series.label.toLowerCase()}`,
  ).join(", ")}`;

  return (
    <button
      type="button"
      className="group relative flex h-full flex-1 cursor-default flex-col items-center justify-end rounded-sm outline-none hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.06]"
      aria-label={summary}
    >
      <div className="flex w-[62%] max-w-6 flex-col-reverse gap-0.5">
        {visible.map((series, segment) => (
          <div
            key={series.key}
            style={{
              height: Math.max((day[series.key] / top) * PLOT_HEIGHT - 2, 2),
              background: series.color,
              // Only the end of the bar is rounded. The baseline stays square.
              borderRadius: segment === visible.length - 1 ? "4px 4px 0 0" : 0,
            }}
          />
        ))}
      </div>

      <div
        className={`pointer-events-none absolute bottom-full z-10 mb-1 hidden w-44 rounded-md border bg-popover p-2 text-xs text-popover-foreground shadow-md group-hover:block group-focus-visible:block ${align}`}
      >
        <p className="mb-1 font-medium">{formatDay(day.day)}</p>
        {[...SERIES].reverse().map((series) => (
          <p key={series.key} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span
                className="size-2 rounded-[2px]"
                style={{ background: series.color }}
                aria-hidden
              />
              {series.label}
            </span>
            <span className="tabular-nums">{formatNumber(day[series.key])}</span>
          </p>
        ))}
        <p className="mt-1 flex justify-between border-t pt-1 font-medium">
          Total <span className="tabular-nums">{formatNumber(total)}</span>
        </p>
      </div>
    </button>
  );
}
