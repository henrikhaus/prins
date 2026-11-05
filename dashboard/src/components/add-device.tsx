import { getRouteApi, useRouter } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { Check, Copy, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

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
import { createDeviceFn, revokeDeviceFn } from "@/server/fns";

const appRoute = getRouteApi("/_app");

type Created = { id: string; name: string; token: string };

/**
 * Name it, paste the token, and the dialog tells you the moment the device has connected.
 * Pass `existing` to skip the name and get a new token for a device that never connected.
 */
export function AddDeviceDialog({
  open,
  onOpenChange,
  existing,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existing?: { id: string; name: string };
}) {
  const router = useRouter();
  const create = useServerFn(createDeviceFn);
  const revoke = useServerFn(revokeDeviceFn);
  const { devices } = appRoute.useLoaderData();
  const [created, setCreated] = useState<Created | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open || !existing || created) return;
    let current = true;
    // A device that never connected has nothing to lose, so swap it for a new one of the same name.
    void revoke({ data: { deviceId: existing.id } })
      .then(() => create({ data: { name: existing.name } }))
      .then((device) => {
        if (current) setCreated(device);
      });
    return () => {
      current = false;
    };
  }, [open, existing, created, create, revoke]);

  const connected = created
    ? devices.some((device) => device.id === created.id && device.lastSeenAt)
    : false;
  const snippet = created
    ? `PRINS_CLOUD_URL=${typeof window === "undefined" ? "" : window.location.origin}\nPRINS_CLOUD_TOKEN=${created.token}`
    : "";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name")).trim();
    if (!name) {
      setError("Give it a name first.");
      return;
    }
    setError(null);
    try {
      setCreated(await create({ data: { name } }));
      await router.invalidate();
    } catch {
      setError("Couldn't add the device. Give it a name of up to 60 characters.");
    }
  };

  const close = (next: boolean) => {
    onOpenChange(next);
    if (!next) {
      setCreated(null);
      setCopied(false);
      setError(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:!max-w-lg">
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>Connect {created.name}</DialogTitle>
              <DialogDescription>
                Add these two lines to the <code className="font-mono">.env</code> file next to
                Prins on your Mac, then run <code className="font-mono">prins run</code> again.
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-2">
              <pre className="rounded-xl bg-muted p-3.5 font-mono text-xs leading-relaxed break-all whitespace-pre-wrap">
                {snippet}
              </pre>
              <Button
                variant="outline"
                className="w-full"
                onClick={async () => {
                  await navigator.clipboard.writeText(snippet);
                  setCopied(true);
                }}
              >
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                {copied ? "Copied" : "Copy both lines"}
              </Button>
              <p className="text-xs text-muted-foreground">
                We only show this token once. If you lose it, you can get a new one from Devices.
              </p>
            </div>
            <p role="status" className="flex items-center gap-2 text-sm">
              {connected ? (
                <>
                  <span className="live-dot" data-online="true" aria-hidden />
                  {created.name} is connected.
                </>
              ) : (
                <>
                  <LoaderCircle
                    className="size-4 animate-spin text-muted-foreground motion-reduce:animate-none"
                    aria-hidden
                  />
                  <span className="text-muted-foreground">Waiting for it to connect...</span>
                </>
              )}
            </p>
            <DialogFooter>
              <Button variant={connected ? "default" : "outline"} onClick={() => close(false)}>
                {connected ? "Done" : "I'll finish this later"}
              </Button>
            </DialogFooter>
          </>
        ) : existing ? (
          <DialogHeader>
            <DialogTitle>Getting a new token...</DialogTitle>
            <DialogDescription>The old one stops working.</DialogDescription>
          </DialogHeader>
        ) : (
          <form onSubmit={submit} noValidate className="flex flex-col gap-5">
            <DialogHeader>
              <DialogTitle>Add a device</DialogTitle>
              <DialogDescription>
                You'll get a token for connecting Prins on your Mac.
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="device-name">Name</Label>
              <Input
                id="device-name"
                name="name"
                maxLength={60}
                placeholder="Office desk"
                aria-invalid={error ? true : undefined}
                autoFocus
              />
              {error ? (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              ) : null}
            </div>
            <DialogFooter>
              <Button type="submit">Create token</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
