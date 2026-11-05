import { Check, CircleOff, Minus, Wifi } from "lucide-react";

import type { DeviceStatus } from "@/server/schema";

import { Badge } from "@/components/ui/badge";
import { timeAgo } from "@/lib/format";

export type DeviceRow = {
  id: string;
  name: string;
  status: DeviceStatus | null;
  isDemo: boolean;
  createdAt: Date;
  lastSeenAt: Date | null;
  online: boolean;
};

const PRINTER_LABELS: Record<string, string> = {
  preview: "Preview only, no paper",
  atech: "Built-in printer",
  serial: "Printer on the Mac",
};

export function OnlineBadge({ device }: { device: DeviceRow }) {
  if (device.online) {
    return (
      <Badge variant="secondary">
        <Wifi aria-hidden />
        Online
      </Badge>
    );
  }
  return (
    <Badge variant="outline">
      <CircleOff aria-hidden />
      {/* Relative to now, so the server and the browser can differ by a moment. */}
      <span suppressHydrationWarning>
        {device.lastSeenAt ? `Seen ${timeAgo(device.lastSeenAt)}` : "Never connected"}
      </span>
    </Badge>
  );
}

export function StatusList({ device }: { device: DeviceRow }) {
  const status = device.status;
  if (!status) {
    return <p className="text-sm text-muted-foreground">Waiting for the first connection.</p>;
  }
  const rows = [
    {
      label: "Board",
      ok: status.deviceKind === "atech",
      value: status.deviceKind === "atech" ? "Connected" : "Simulated",
    },
    {
      label: "Printer",
      ok: status.printer !== "preview",
      value: PRINTER_LABELS[status.printer] ?? status.printer,
    },
    {
      label: "Dictation",
      ok: status.handyInstalled,
      value: status.handyInstalled ? "Handy ready" : "Not installed",
    },
    { label: "Slack", ok: status.slack, value: status.slack ? "Connected" : "Not set up" },
    { label: "Email", ok: status.email, value: status.email ? "Connected" : "Not set up" },
  ];
  return (
    <dl className="flex flex-col gap-2 text-sm">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center justify-between gap-3">
          <dt className="text-muted-foreground">{row.label}</dt>
          <dd className="flex items-center gap-1.5 text-right">
            {row.ok ? (
              <Check className="size-3.5 shrink-0" aria-hidden />
            ) : (
              <Minus className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            )}
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
