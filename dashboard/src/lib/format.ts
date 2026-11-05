/**
 * One fixed zone, used on both server and browser. If each used its own, the server's rendered
 * dates would differ from the browser's and React would throw away the page on load.
 */
export const TIME_ZONE = "Europe/Oslo";

const SOURCE_LABELS: Record<string, string> = {
  slack: "Slack",
  email: "Email",
  voice: "Voice",
  agent: "Agent",
};

export const sourceLabel = (source: string) =>
  SOURCE_LABELS[source] ?? source.charAt(0).toUpperCase() + source.slice(1);

export const STATUS_LABELS = {
  queued: "In queue",
  printed: "Printed",
  dismissed: "Dismissed",
  ignored: "Filtered",
} as const;

const number = new Intl.NumberFormat("en-US");
export const formatNumber = (value: number) => number.format(value);

const dateTime = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: TIME_ZONE,
});
/** Built from parts because Bun writes "5 Nov at 17:00" and Chrome "5 Nov, 17:00". */
export function formatDateTime(date: Date) {
  const part = Object.fromEntries(dateTime.formatToParts(date).map((p) => [p.type, p.value]));
  return `${part.day} ${part.month}, ${part.hour}:${part.minute}`;
}

const clock = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: TIME_ZONE,
});
export function formatTime(date: Date) {
  const part = Object.fromEntries(clock.formatToParts(date).map((p) => [p.type, p.value]));
  return `${part.hour}:${part.minute}`;
}

const dayOf = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  timeZone: TIME_ZONE,
});
/** A heading for a day of history, such as "Thursday 5 November". */
export function formatDayHeading(date: Date) {
  const part = Object.fromEntries(dayOf.formatToParts(date).map((p) => [p.type, p.value]));
  return `${part.weekday} ${part.day} ${part.month}`;
}

const shortDay = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
/** `day` is a calendar date such as 2026-11-05, already in the right time zone. */
export function formatDay(day: string) {
  const parts = shortDay.formatToParts(new Date(`${day}T00:00:00Z`));
  const part = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${part.day} ${part.month}`;
}

export function timeAgo(date: Date, now = Date.now()) {
  const seconds = Math.max(0, Math.round((now - date.getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** The next round number at or above `value`, for a chart's top gridline. */
export function niceCeiling(value: number) {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 3, 4, 5, 6, 8, 10].find((candidate) => candidate * magnitude >= value) ?? 10;
  return step * magnitude;
}
