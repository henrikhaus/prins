import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { Check, Copy, Plus } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { PageHeader, Panel } from "@/components/app-shell";
import { OnlineBadge, StatusList } from "@/components/device-status";
import type { DeviceRow } from "@/components/device-status";
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
import { createDeviceFn, getDevicesFn, revokeDeviceFn } from "@/server/fns";

export const Route = createFileRoute("/_app/devices")({
  loader: () => getDevicesFn(),
  head: () => ({ meta: [{ title: "Devices - Prins" }] }),
  component: DevicesPage,
});

function DevicesPage() {
  const devices = Route.useLoaderData();
  const [adding, setAdding] = useState(false);

  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <PageHeader title="Devices" description="Each device syncs its queue and status here." />
        <Button onClick={() => setAdding(true)}>
          <Plus aria-hidden />
          Add device
        </Button>
      </div>

      {devices.length === 0 ? (
        <Panel>
          <p className="text-sm text-muted-foreground">
            No devices yet. Add one to get a connection token.
          </p>
        </Panel>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {devices.map((device) => (
            <DeviceCard key={device.id} device={device} />
          ))}
        </div>
      )}

      <AddDeviceDialog open={adding} onOpenChange={setAdding} />
    </>
  );
}

function DeviceCard({ device }: { device: DeviceRow }) {
  const router = useRouter();
  const revoke = useServerFn(revokeDeviceFn);
  const [confirming, setConfirming] = useState(false);

  const confirmRevoke = async () => {
    await revoke({ data: { deviceId: device.id } });
    setConfirming(false);
    await router.invalidate();
  };

  return (
    <Panel>
      <div className="mb-4 flex items-center justify-between gap-2">
        <h2 className="truncate font-medium">{device.name}</h2>
        <OnlineBadge device={device} />
      </div>
      <StatusList device={device} />
      <Button
        variant="ghost"
        size="sm"
        className="mt-4 -ml-2 text-muted-foreground"
        onClick={() => setConfirming(true)}
      >
        Disconnect
      </Button>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect {device.name}?</DialogTitle>
            <DialogDescription>
              Its token stops working right away. Its history stays, and the device keeps working on
              its own. To reconnect, add it again and use a new token.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
            <Button variant="destructive" onClick={confirmRevoke}>
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Panel>
  );
}

function AddDeviceDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const create = useServerFn(createDeviceFn);
  const [created, setCreated] = useState<{ name: string; token: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const snippet = created
    ? `PRINS_CLOUD_URL=${typeof window === "undefined" ? "" : window.location.origin}\nPRINS_CLOUD_TOKEN=${created.token}`
    : "";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      const device = await create({
        data: { name: String(new FormData(event.currentTarget).get("name")) },
      });
      setCreated(device);
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
      <DialogContent>
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>Connect {created.name}</DialogTitle>
              <DialogDescription>
                Add this to the <code>.env</code> file next to the Prins daemon, then restart it.{" "}
                <strong>The token is only shown now.</strong>
              </DialogDescription>
            </DialogHeader>
            <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">{snippet}</pre>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={async () => {
                  await navigator.clipboard.writeText(snippet);
                  setCopied(true);
                }}
              >
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                {copied ? "Copied" : "Copy"}
              </Button>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>Add a device</DialogTitle>
              <DialogDescription>
                You'll get a token for connecting the daemon on your Mac.
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="device-name">Name</Label>
              <Input
                id="device-name"
                name="name"
                required
                maxLength={60}
                placeholder="Office desk"
              />
            </div>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="submit">Create token</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
