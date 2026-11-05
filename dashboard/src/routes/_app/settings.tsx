import { createFileRoute, useRouter } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { PageHeader, Section, ThemeChoice } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";

export const Route = createFileRoute("/_app/settings")({
  head: () => ({ meta: [{ title: "Settings - Prins" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  const { session } = Route.useRouteContext();
  return (
    <>
      <PageHeader title="Settings" />
      <div className="mx-auto flex w-full max-w-xl flex-col gap-12 md:mx-0">
        <Profile name={session.name} email={session.email} />
        <Password />
        <Section title="Appearance">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm">Theme</span>
            <ThemeChoice />
          </div>
        </Section>
      </div>
    </>
  );
}

function Saved({ text }: { text: string }) {
  return (
    <span role="status" className="flex items-center gap-1.5 text-sm text-muted-foreground">
      <Check className="size-4" style={{ color: "var(--key-print)" }} aria-hidden />
      {text}
    </span>
  );
}

function Profile({ name, email }: { name: string; email: string }) {
  const router = useRouter();
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next = String(new FormData(event.currentTarget).get("name")).trim();
    setSaved(false);
    if (!next) {
      setError("Friends see this name, so it can't be empty.");
      return;
    }
    setError(null);
    const result = await authClient.updateUser({ name: next });
    if (result.error) {
      setError("That didn't save. Try again.");
      return;
    }
    setSaved(true);
    await router.invalidate();
  };

  return (
    <Section title="Profile">
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="settings-name">Name</Label>
          <Input
            id="settings-name"
            name="name"
            defaultValue={name}
            maxLength={100}
            aria-invalid={error ? true : undefined}
            onChange={() => setSaved(false)}
          />
          <p className="text-xs text-muted-foreground">
            {error ? <span className="text-destructive">{error}</span> : "Friends see this name."}
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="settings-email">Email</Label>
          <Input id="settings-email" value={email} readOnly disabled />
        </div>
        <div className="flex items-center gap-3">
          <Button type="submit">Save</Button>
          {saved ? <Saved text="Saved" /> : null}
        </div>
      </form>
    </Section>
  );
}

function Password() {
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const currentPassword = String(data.get("current"));
    const newPassword = String(data.get("next"));
    setSaved(false);
    if (!currentPassword) {
      setError("Enter your current password.");
      return;
    }
    if (newPassword.length < 10) {
      setError("Your new password needs at least 10 characters.");
      return;
    }
    setError(null);
    const result = await authClient.changePassword({ currentPassword, newPassword });
    if (result.error) {
      setError(
        result.error.code === "INVALID_PASSWORD"
          ? "That isn't your current password."
          : "That didn't save. Try again.",
      );
      return;
    }
    form.reset();
    setSaved(true);
  };

  return (
    <Section title="Password">
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="current-password">Current password</Label>
          <Input
            id="current-password"
            name="current"
            type="password"
            autoComplete="current-password"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-password">New password</Label>
          <Input id="new-password" name="next" type="password" autoComplete="new-password" />
          <p className="text-xs text-muted-foreground">At least 10 characters.</p>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <div className="flex items-center gap-3">
          <Button type="submit" variant="outline">
            Change password
          </Button>
          {saved ? <Saved text="Password changed" /> : null}
        </div>
      </form>
    </Section>
  );
}
