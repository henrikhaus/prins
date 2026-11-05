import { createFileRoute, redirect, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { getAuthConfigFn, getSessionFn } from "@/server/fns";

export const Route = createFileRoute("/login")({
  beforeLoad: async () => {
    if (await getSessionFn()) throw redirect({ to: "/" });
  },
  loader: () => getAuthConfigFn(),
  component: LoginPage,
});

function LoginPage() {
  const { signUpAllowed } = Route.useLoaderData();
  const router = useRouter();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    setBusy(true);
    setError(null);
    const result =
      mode === "in"
        ? await authClient.signIn.email({ email, password })
        : await authClient.signUp.email({ email, password, name: String(form.get("name")) });
    setBusy(false);
    if (result.error) {
      setError(result.error.message ?? "That didn't work. Check your details and try again.");
      return;
    }
    await router.invalidate();
    await router.navigate({ to: "/" });
  };

  return (
    <main className="mx-auto flex min-h-svh max-w-sm flex-col justify-center gap-6 px-4 py-10">
      <div className="note-paper -rotate-1 rounded-[3px] p-5">
        <p className="text-xs tracking-wide">PRINS</p>
        <hr className="my-2 border-t-2 border-black" />
        <p className="text-xl leading-snug font-bold text-balance">
          200 messages hit your inbox. Five sticky notes reach your desk.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <h1 className="text-lg font-semibold">
          {mode === "in" ? "Sign in" : "Create your account"}
        </h1>
        {mode === "up" ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" name="name" required autoComplete="name" />
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" name="email" type="email" required autoComplete="email" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            name="password"
            type="password"
            required
            minLength={mode === "up" ? 10 : undefined}
            autoComplete={mode === "in" ? "current-password" : "new-password"}
          />
          {mode === "up" ? (
            <p className="text-xs text-muted-foreground">At least 10 characters.</p>
          ) : null}
        </div>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={busy}>
          {busy ? "One moment..." : mode === "in" ? "Sign in" : "Create account"}
        </Button>
        {signUpAllowed ? (
          <button
            type="button"
            className="text-sm text-muted-foreground underline underline-offset-4"
            onClick={() => {
              setMode(mode === "in" ? "up" : "in");
              setError(null);
            }}
          >
            {mode === "in" ? "Need an account? Create one" : "Already have an account? Sign in"}
          </button>
        ) : null}
      </form>
    </main>
  );
}
