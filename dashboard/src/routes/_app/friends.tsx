import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { Check, Copy, Send, UserPlus } from "lucide-react";
import { useOptimistic, useRef, useState, useTransition } from "react";
import type { FormEvent } from "react";

import { PageHeader, Panel } from "@/components/app-shell";
import { DrawPad } from "@/components/draw-pad";
import type { DrawPadHandle } from "@/components/draw-pad";
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

function FriendsPage() {
  const { code, friends, incoming, outgoing, sent } = Route.useLoaderData();
  const router = useRouter();
  const addFriend = useServerFn(addFriendFn);
  const respond = useServerFn(respondFriendFn);
  const remove = useServerFn(removeFriendFn);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [sendingTo, setSendingTo] = useState<Friend | null>(null);

  const onAdd = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const value = String(new FormData(form).get("code") ?? "");
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
    <>
      <PageHeader
        title="Friends"
        description="Let friends put notes in your queue. Nothing prints until you press the button."
      />

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Your friend code">
          <div className="flex items-center justify-between gap-3">
            <code className="text-xl font-semibold tracking-wider">{code}</code>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                await navigator.clipboard.writeText(code);
                setCopied(true);
              }}
            >
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Share it with someone so they can add you.
          </p>
        </Panel>

        <Panel title="Add a friend">
          <form onSubmit={onAdd} className="flex gap-2">
            <Input
              name="code"
              required
              placeholder="ABCD-EFGH"
              aria-label="Friend code"
              className="uppercase placeholder:normal-case"
            />
            <Button type="submit">
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
        </Panel>
      </div>

      {incoming.length > 0 ? (
        <Panel title="Friend requests">
          <ul className="flex flex-col gap-3">
            {incoming.map((request) => (
              <li
                key={request.friendshipId}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span className="min-w-0 truncate font-medium">{request.name}</span>
                <span className="flex shrink-0 gap-2">
                  <Button
                    size="sm"
                    onClick={async () => {
                      await respond({ data: { friendshipId: request.friendshipId, accept: true } });
                      await router.invalidate();
                    }}
                  >
                    Accept
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={async () => {
                      await respond({
                        data: { friendshipId: request.friendshipId, accept: false },
                      });
                      await router.invalidate();
                    }}
                  >
                    Decline
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <Panel title={friends.length === 1 ? "1 friend" : `${friends.length} friends`}>
        {friends.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No friends yet. Share your code to get started.
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
          <p className="mt-3 text-sm text-muted-foreground">
            Waiting for an answer from {outgoing.map((request) => request.name).join(", ")}.
          </p>
        ) : null}
      </Panel>

      {sent.length > 0 ? (
        <Panel title="Notes you've sent">
          <ul className="flex flex-col gap-2 text-sm">
            {sent.map((note) => (
              <li key={note.id} className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 truncate">
                  <span className="font-medium">{note.recipient}:</span> {note.title}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {note.deliveredAt ? "Delivered" : "Waiting for their device"} ·{" "}
                  {formatDateTime(note.createdAt)}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <SendNoteDialog friend={sendingTo} onClose={() => setSendingTo(null)} />
    </>
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

  // Ticks at once, and returns to the saved value by itself if saving fails.
  const onPermission = (allowed: boolean) => {
    startTransition(async () => {
      showPermission(allowed);
      await setPermission({ data: { friendId: friend.id, allowed } });
      await router.invalidate();
    });
  };

  return (
    <li className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="truncate font-medium">{friend.name}</p>
        <label className="mt-1 flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            className="size-4 accent-foreground"
            checked={canPrintToMe}
            onChange={(event) => onPermission(event.target.checked)}
          />
          Can send notes to my Prins
        </label>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {friend.canPrintToThem ? (
          <Button size="sm" onClick={onSend}>
            <Send aria-hidden />
            Send a note
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">They haven't let you send notes yet</span>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="text-muted-foreground"
          onClick={() => setConfirming(true)}
        >
          Remove
        </Button>
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

function SendNoteDialog({ friend, onClose }: { friend: Friend | null; onClose: () => void }) {
  const router = useRouter();
  const send = useServerFn(sendNoteFn);
  const pad = useRef<DrawPadHandle>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!friend) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const result = await send({
        data: {
          friendId: friend.id,
          title: String(form.get("title")),
          detail: String(form.get("detail") ?? ""),
          bitmap: pad.current?.bitmap() ?? null,
        },
      });
      if (result.ok) {
        onClose();
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
    <Dialog open={friend !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Send {friend?.name} a note</DialogTitle>
            <DialogDescription>
              They'll see it on their device and press a button to print it. If you draw something,
              your drawing is what prints.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="note-title">Message</Label>
            <Input
              id="note-title"
              name="title"
              required
              maxLength={120}
              placeholder="Good luck today!"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="note-detail">More detail (optional)</Label>
            <Input id="note-detail" name="detail" maxLength={200} />
          </div>
          <DrawPad ref={pad} />
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
