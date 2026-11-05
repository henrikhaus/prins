import { Check, Minus } from "lucide-react";

import type { DeviceStatus } from "@/server/schema";

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

export function OnlineLabel({ device }: { device: DeviceRow }) {
  return (
    <span className="flex items-center gap-2 text-sm">
      <span className="live-dot" data-online={device.online} aria-hidden />
      {device.online ? (
        "Online"
      ) : (
        // Relative to now, so the server and the browser can differ by a moment.
        <span className="text-muted-foreground" suppressHydrationWarning>
          {device.lastSeenAt ? `Last seen ${timeAgo(device.lastSeenAt)}` : "Never connected"}
        </span>
      )}
    </span>
  );
}

export function StatusList({ device }: { device: DeviceRow }) {
  const status = device.status;
  if (!status) {
    return null;
  }
  const rows: { label: string; ok: boolean; value: string; hint?: string }[] = [
    {
      label: "Hardware",
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
      value: status.handyInstalled ? "Ready" : "Not installed",
      hint: status.handyInstalled ? undefined : "Install Handy on your Mac to talk to your Prins.",
    },
    {
      label: "Slack",
      ok: status.slack,
      value: status.slack ? "Connected" : "Not set up",
      hint: status.slack ? undefined : "Add your SLACK_ tokens to the .env on your Mac.",
    },
    {
      label: "Email",
      ok: status.email,
      value: status.email ? "Connected" : "Not set up",
      hint: status.email ? undefined : "Add your PRINS_IMAP_ details to the .env on your Mac.",
    },
  ];
  return (
    <dl className="grid gap-x-10 sm:grid-cols-2">
      {rows.map((row) => (
        <div key={row.label} className="border-t py-2.5 text-sm">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">{row.label}</dt>
            <dd
              className={`flex items-center gap-1.5 text-right ${row.ok ? "" : "text-muted-foreground"}`}
            >
              {row.ok ? (
                <Check
                  className="size-3.5 shrink-0"
                  style={{ color: "var(--key-print)" }}
                  aria-hidden
                />
              ) : (
                <Minus className="size-3.5 shrink-0" aria-hidden />
              )}
              {row.value}
            </dd>
          </div>
          {row.hint ? <dd className="mt-1 text-xs text-muted-foreground">{row.hint}</dd> : null}
        </div>
      ))}
    </dl>
  );
}
