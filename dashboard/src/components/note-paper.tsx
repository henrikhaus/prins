import { NoteBitmap } from "@/components/note-bitmap";
import { formatDateTime, sourceLabel } from "@/lib/format";

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

export const originOf = (item: Pick<QueueItem, "source" | "sender">) =>
  sourceLabel(item.source) + (item.sender ? ` - ${item.sender}` : "");

/**
 * A note on paper, in the 312x216 proportions of a real one. Everything is sized to the width, so
 * it looks the same on a phone and on the desk. Black on white in dark mode too.
 */
export function NotePaper({
  item,
  className = "",
  flat = false,
  placeholder = false,
}: {
  item: Pick<
    QueueItem,
    "source" | "sender" | "title" | "detail" | "priority" | "due" | "bitmap"
  > & {
    createdAt?: Date;
  };
  className?: string;
  /** A note lying under another one: bare paper, because only its edge shows. */
  flat?: boolean;
  /** The title is an example, shown while the real one hasn't been written yet. */
  placeholder?: boolean;
}) {
  return (
    <div className={`${flat ? "" : "note-shadow "}[container-type:inline-size] ${className}`}>
      <div
        className={`${flat ? "note-under" : "note-paper"} note-tear aspect-[312/216] w-full overflow-hidden`}
      >
        {flat ? null : item.bitmap ? (
          <NoteBitmap bitmap={item.bitmap} label={item.title} />
        ) : (
          <article className="flex h-full flex-col px-[5.5cqw] pt-[4.5cqw] pb-[5.5cqw]">
            <div className="flex items-baseline justify-between gap-[3cqw] font-mono text-[3cqw] leading-tight">
              <span className="truncate uppercase">{originOf(item)}</span>
              {item.priority === "high" ? (
                <span className="shrink-0 bg-black px-[1.2cqw] text-white">URGENT</span>
              ) : null}
            </div>
            <hr className="mt-[2cqw] mb-[3.5cqw] border-t-[0.5cqw] border-black" />
            <h3
              className={`line-clamp-3 text-[8cqw] leading-[1.06] font-bold tracking-[-0.025em] text-balance ${
                placeholder ? "opacity-25" : ""
              }`}
            >
              {item.title}
            </h3>
            {item.detail ? (
              <p className="mt-[2.5cqw] line-clamp-2 text-[3.7cqw] leading-snug">{item.detail}</p>
            ) : null}
            <p className="mt-auto truncate font-mono text-[2.8cqw] leading-tight">
              {item.due ? `Due ${item.due}` : item.createdAt ? formatDateTime(item.createdAt) : ""}
            </p>
          </article>
        )}
      </div>
    </div>
  );
}
