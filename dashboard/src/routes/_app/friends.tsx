import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { Check, Copy, PenLine, Send, Type, UserPlus } from "lucide-react";
import { useOptimistic, useRef, useState, useTransition } from "react";
import type { FormEvent } from "react";

import { PageHeader, Section } from "@/components/app-shell";
import { DrawPad } from "@/components/draw-pad";
import type { DrawPadHandle } from "@/components/draw-pad";
import { NotePaper } from "@/components/note-paper";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { formatDateTime } from "@/lib/format";
import {
  addFriendFn,
  getFriendsFn,
  removeFriendFn,
  respondFriendFn,
  sendNoteFn,
  setPermissionFn,
} from "@/server/fns";

export const Route = createFileRoute("/_app/friends")({
  loader: () => getFriendsFn(),
  head: () => ({ meta: [{ title: "Friends - Prins" }] }),
  component: FriendsPage,
});

type Friend = { id: string; name: string; canPrintToMe: boolean; canPrintToThem: boolean };

function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden
      className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground uppercase"
    >
      {name.charAt(0)}
    </span>
  );
}

function FriendsPage() {
  const { code, friends, incoming, outgoing, sent } = Route.useLoaderData();
  const router = useRouter();
  const respond = useServerFn(respondFriendFn);
  const setPermission = useServerFn(setPermissionFn);
  const remove = useServerFn(removeFriendFn);
  const loadFriends = useServerFn(getFriendsFn);
  const [sendingTo, setSendingTo] = useState<Friend | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const answer = async (friendshipId: number, allow: boolean | null) => {
    const known = new Set(friends.map((friend) => friend.id));
    await respond({ data: { friendshipId, accept: allow !== null } });
    if (allow) {
      // The new friend is whoever appears on the list now that the request is accepted.
      const fresh = await loadFriends();
      const added = fresh.friends.find((friend) => !known.has(friend.id));
      if (added) await setPermission({ data: { friendId: added.id, allowed: true } });
    }
    await router.invalidate();
  };

  return (
    <>
      <PageHeader
        title="Friends"
        description="Let friends put notes in your queue. Nothing prints until you press the button."
      />

      <div className="grid gap-x-16 gap-y-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-10">
          {incoming.map((request) => (
            <section
              key={request.friendshipId}
              className="rise-in flex flex-col gap-4 rounded-3xl bg-hot p-6 text-hot-foreground"
            >
              <div>
                <h2 className="text-xl font-medium tracking-[-0.02em]">
                  {request.name} wants to be friends
                </h2>
                <p className="mt-1 text-sm opacity-80">
                  You choose whether they can send notes to your Prins. You can change it later.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  className="bg-hot-foreground text-hot hover:bg-hot-foreground/85"
                  onClick={() => answer(request.friendshipId, true)}
                >
                  Accept and allow notes
                </Button>
                <Button
                  variant="ghost"
                  className="hover:bg-hot-foreground/10 hover:text-hot-foreground"
                  onClick={() => answer(request.friendshipId, false)}
                >
                  Accept only
                </Button>
                <Button
                  variant="ghost"
                  className="hover:bg-hot-foreground/10 hover:text-hot-foreground"
                  onClick={() => answer(request.friendshipId, null)}
                >
                  Decline
                </Button>
              </div>
            </section>
          ))}

          <Section title={friends.length === 1 ? "1 friend" : `${friends.length} friends`}>
            {friends.length === 0 ? (
              <p className="py-6 text-muted-foreground">
                No friends yet. Share your code, or add someone with theirs.
              </p>
            ) : (
              <ul className="flex flex-col divide-y">
                {friends.map((friend) => (
                  <FriendRow
                    key={friend.id}
                    friend={friend}
                    onSend={() => setSendingTo(friend)}
                    onRemove={async () => {
                      await remove({ data: { friendId: friend.id } });
                      await router.invalidate();
                    }}
                  />
                ))}
              </ul>
            )}
            {outgoing.length > 0 ? (
              <p className="mt-4 text-sm text-muted-foreground">
                Waiting for an answer from {outgoing.map((request) => request.name).join(", ")}.
              </p>
            ) : null}
          </Section>

          {notice ? (
            <p role="status" className="rise-in flex items-center gap-2 text-sm font-medium">
              <Check className="size-4" style={{ color: "var(--key-print)" }} aria-hidden />
              {notice}
            </p>
          ) : null}

          {sent.length > 0 ? (
            <Section title="Notes you've sent">
              <ul className="flex flex-col divide-y text-sm">
                {sent.map((note) => (
                  <li key={note.id} className="min-w-0 py-2.5">
                    <span className="min-w-0">
                      <span className="block truncate">
                        <span className="font-medium">{note.recipient}:</span> {note.title}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {note.deliveredAt ? "Delivered" : "Waiting for their device"} ·{" "}
                        {formatDateTime(note.createdAt)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}
        </div>

        <aside className="flex min-w-0 flex-col gap-10">
          <FriendCode code={code} />
          <AddFriend />
        </aside>
      </div>

      <SendNoteDialog
        friend={sendingTo}
        onClose={() => setSendingTo(null)}
        onSent={(name) => setNotice(`Sent to ${name}. They'll approve it before it prints.`)}
      />
    </>
  );
}

function FriendCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Section title="Your friend code">
      <button
        type="button"
        className="group flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl bg-muted p-4 text-left transition-colors hover:bg-accent"
        onClick={async () => {
          await navigator.clipboard.writeText(code);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }}
      >
        <code className="font-mono text-xl font-medium tracking-wider">{code}</code>
        <span className="flex shrink-0 items-center gap-1.5 text-[0.8125rem] text-muted-foreground group-hover:text-foreground">
          {copied ? (
            <Check className="size-3.5" aria-hidden />
          ) : (
            <Copy className="size-3.5" aria-hidden />
          )}
          {copied ? "Copied" : "Copy"}
        </span>
      </button>
      <p className="mt-2 text-sm text-pretty text-muted-foreground">
        Share it with someone so they can add you.
      </p>
    </Section>
  );
}

function AddFriend() {
  const router = useRouter();
  const addFriend = useServerFn(addFriendFn);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const onAdd = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    // People retype codes without the hyphen, or paste them with a space.
    const compact = String(new FormData(form).get("code") ?? "")
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
    const value = compact.length === 8 ? `${compact.slice(0, 4)}-${compact.slice(4)}` : compact;
    if (!value) {
      setMessage({ ok: false, text: "Enter their code first." });
      return;
    }
    try {
      const result = await addFriend({ data: { code: value } });
      setMessage({ ok: result.ok, text: result.message });
      if (result.ok) form.reset();
    } catch {
      setMessage({ ok: false, text: "That doesn't look like a friend code." });
    }
    await router.invalidate();
  };

  return (
    <Section title="Add a friend">
      <form onSubmit={onAdd} noValidate className="flex gap-2">
        <Input
          name="code"
          placeholder="ABCD-EFGH"
          aria-label="Friend code"
          className="font-mono uppercase placeholder:normal-case"
        />
        <Button type="submit" variant="outline" className="h-11 shrink-0">
          <UserPlus aria-hidden />
          Add
        </Button>
      </form>
      {message ? (
        <p
          role="status"
          className={`mt-2 text-sm ${message.ok ? "text-muted-foreground" : "text-destructive"}`}
        >
          {message.text}
        </p>
      ) : null}
    </Section>
  );
}

function FriendRow({
  friend,
  onSend,
  onRemove,
}: {
  friend: Friend;
  onSend: () => void;
  onRemove: () => void;
}) {
  const router = useRouter();
  const setPermission = useServerFn(setPermissionFn);
  const [confirming, setConfirming] = useState(false);
  const [canPrintToMe, showPermission] = useOptimistic(friend.canPrintToMe);
  const [, startTransition] = useTransition();

  // Switches at once, and returns to the saved value by itself if saving fails.
  const onPermission = (allowed: boolean) => {
    startTransition(async () => {
      showPermission(allowed);
      await setPermission({ data: { friendId: friend.id, allowed } });
      await router.invalidate();
    });
  };

  return (
    <li className="flex flex-col gap-4 py-4 first:pt-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3.5">
        <Avatar name={friend.name} />
        <div className="min-w-0">
          <p className="truncate font-medium">{friend.name}</p>
          <label className="mt-1 flex cursor-pointer items-center gap-2 text-[0.8125rem] text-muted-foreground">
            <Switch checked={canPrintToMe} onCheckedChange={onPermission} />
            Can send to my Prins
          </label>
        </div>
      </div>
      <div className="flex shrink-0 flex-col gap-1 sm:items-end">
        <div className="flex items-center gap-1">
          <Button size="sm" onClick={onSend} disabled={!friend.canPrintToThem}>
            <Send aria-hidden />
            Send a note
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-muted-foreground"
            onClick={() => setConfirming(true)}
          >
            Remove
          </Button>
        </div>
        {friend.canPrintToThem ? null : (
          <p className="text-xs text-muted-foreground">
            {friend.name} hasn't allowed notes from you yet.
          </p>
        )}
      </div>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove {friend.name}?</DialogTitle>
            <DialogDescription>
              Neither of you will be able to send notes to the other. Notes that haven't reached a
              device yet are cancelled.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Keep
            </Button>
            <Button variant="destructive" onClick={onRemove}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  );
}

const TITLE_MAX = 120;

function SendNoteDialog({
  friend,
  onClose,
  onSent,
}: {
  friend: Friend | null;
  onClose: () => void;
  onSent: (name: string) => void;
}) {
  const router = useRouter();
  const send = useServerFn(sendNoteFn);
  const pad = useRef<DrawPadHandle>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"write" | "draw">("write");
  const [title, setTitle] = useState("");
  const [detail, setDetail] = useState("");

  const reset = () => {
    setTitle("");
    setDetail("");
    setMode("write");
    setError(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!friend) return;
    if (!title.trim()) {
      setError(mode === "draw" ? "Add a caption for their screen." : "Write something first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await send({
        data: {
          friendId: friend.id,
          title,
          detail,
          bitmap: mode === "draw" ? (pad.current?.bitmap() ?? null) : null,
        },
      });
      if (result.ok) {
        onSent(friend.name);
        onClose();
        reset();
        await router.invalidate();
      } else {
        setError(result.error);
      }
    } catch {
      setError("That didn't go through. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={friend !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
          reset();
        }
      }}
    >
      <DialogContent className="max-h-[92svh] overflow-y-auto sm:!max-w-lg">
        <form onSubmit={submit} noValidate className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>Send {friend?.name} a note</DialogTitle>
            <DialogDescription>
              They'll see it on their device and press a button to print it.
            </DialogDescription>
          </DialogHeader>

          <div className="flex w-fit gap-0.5 rounded-full bg-muted p-1">
            {(
              [
                ["write", "Write", Type],
                ["draw", "Draw", PenLine],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                type="button"
                aria-pressed={mode === value}
                onClick={() => setMode(value)}
                className={`flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1 text-[0.8125rem] font-medium transition-colors ${
                  mode === value
                    ? "bg-background shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Icon className="size-3.5" aria-hidden />
                {label}
              </button>
            ))}
          </div>

          {/* Hidden, not removed, so switching to Write and back keeps the drawing. */}
          <div className={mode === "draw" ? "" : "hidden"}>
            <DrawPad ref={pad} />
          </div>
          {mode === "write" ? (
            <NotePaper
              className="mx-auto w-full max-w-sm"
              placeholder={!title}
              item={{
                source: "friend",
                sender: "",
                title: title || "Good luck today!",
                detail,
                priority: "normal",
                due: "",
                bitmap: null,
              }}
            />
          ) : null}

          <div className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <Label htmlFor="note-title">
                {mode === "draw" ? "Caption, shown on their screen" : "Message"}
              </Label>
              <span className="font-mono text-xs text-muted-foreground tabular-nums">
                {title.length}/{TITLE_MAX}
              </span>
            </div>
            <Input
              id="note-title"
              maxLength={TITLE_MAX}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              aria-invalid={error ? true : undefined}
              placeholder="Good luck today!"
            />
          </div>
          {mode === "write" ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="note-detail">More detail (optional)</Label>
              <Input
                id="note-detail"
                maxLength={200}
                value={detail}
                onChange={(event) => setDetail(event.target.value)}
              />
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={busy}>
              <Send aria-hidden />
              {busy ? "Sending..." : "Send"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
