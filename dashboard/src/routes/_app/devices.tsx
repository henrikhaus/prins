import { Link, createFileRoute, useRouter } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { ArrowUpRight, Plus, RefreshCw } from "lucide-react";
import { useState } from "react";

import type { DeviceRow } from "@/components/device-status";

import { AddDeviceDialog } from "@/components/add-device";
import { PageHeader } from "@/components/app-shell";
import { OnlineLabel, StatusList } from "@/components/device-status";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getDevicesFn, revokeDeviceFn } from "@/server/fns";

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
      <PageHeader
        title="Devices"
        description="Each device keeps working on its own, and syncs here every few seconds."
        action={
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden />
            Add device
          </Button>
        }
      />

      {devices.length === 0 ? (
        <p className="rise-in border-t py-16 text-center text-muted-foreground">
          No devices yet. Add one to get a connection token.
        </p>
      ) : (
        <div className="flex flex-col gap-12">
          {devices.map((device) => (
            <DeviceBlock key={device.id} device={device} />
          ))}
        </div>
      )}

      <Link
        to="/product"
        viewTransition
        className="on-brand rise-in group mt-auto flex items-center justify-between gap-4 rounded-3xl bg-brand p-6 text-brand-foreground transition-transform duration-300 hover:-translate-y-0.5"
      >
        <span>
          <span className="block text-lg font-medium tracking-tight">See the concept model</span>
          <span className="mt-0.5 block text-sm text-white/80">
            Turn it around and try the three keys in 3D.
          </span>
        </span>
        <ArrowUpRight
          className="size-6 shrink-0 text-hot transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
          aria-hidden
        />
      </Link>

      <AddDeviceDialog open={adding} onOpenChange={setAdding} />
    </>
  );
}

function DeviceBlock({ device }: { device: DeviceRow }) {
  const router = useRouter();
  const revoke = useServerFn(revokeDeviceFn);
  const [confirming, setConfirming] = useState(false);
  const [newToken, setNewToken] = useState(false);
  const neverConnected = !device.lastSeenAt && !device.isDemo;

  const confirmRevoke = async () => {
    await revoke({ data: { deviceId: device.id } });
    setConfirming(false);
    await router.invalidate();
  };

  return (
    <section className="rise-in">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <h2 className="text-2xl font-medium tracking-[-0.02em]">{device.name}</h2>
          <OnlineLabel device={device} />
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="-mr-3 text-muted-foreground"
          onClick={() => setConfirming(true)}
        >
          {neverConnected ? "Remove" : "Disconnect"}
        </Button>
      </div>

      {neverConnected ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-muted p-4 text-sm">
          <span className="max-w-md text-pretty text-muted-foreground">
            Paste its two lines into the .env file on your Mac, then run prins run again. Lost them?
            A new token replaces the old one.
          </span>
          <Button variant="outline" size="sm" onClick={() => setNewToken(true)}>
            <RefreshCw aria-hidden />
            Get a new token
          </Button>
        </div>
      ) : (
        <StatusList device={device} />
      )}

      <AddDeviceDialog open={newToken} onOpenChange={setNewToken} existing={device} />
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {neverConnected ? `Remove ${device.name}?` : `Disconnect ${device.name}?`}
            </DialogTitle>
            <DialogDescription>
              {neverConnected
                ? "It has never connected, so nothing is lost. Its token stops working right away."
                : "Its token stops working right away. Its history stays, and the device keeps working on its own. To reconnect, add it again and use a new token."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
            <Button variant="destructive" onClick={confirmRevoke}>
              {neverConnected ? "Remove" : "Disconnect"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
