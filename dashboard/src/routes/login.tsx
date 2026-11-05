import { createFileRoute, redirect, useRouter } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { Halftone } from "@/components/halftone";
import { NotePaper } from "@/components/note-paper";
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
  head: () => ({ meta: [{ title: "Sign in - Prins" }] }),
  component: LoginPage,
});

const SAMPLE = {
  source: "email",
  sender: "Elena",
  title: "Call Halvorsen Tile back today",
  detail: "She has a question about the sample order.",
  priority: "normal",
  due: "",
  bitmap: null,
};

const PITCH = "Your inbox and your voice, turned into sticky notes you approve with a button.";

function LoginPage() {
  const { signUpAllowed } = Route.useLoaderData();
  const router = useRouter();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email")).trim();
    const password = String(form.get("password"));
    if (mode === "up" && !String(form.get("name")).trim()) {
      setError("Add your name. Friends see it on your notes.");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setError("That doesn't look like an email address.");
      return;
    }
    if (!password || (mode === "up" && password.length < 10)) {
      setError(
        mode === "up" ? "Your password needs at least 10 characters." : "Enter your password.",
      );
      return;
    }
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
    <main className="grid min-h-svh lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
      <div className="flex flex-col justify-between gap-8 p-6 md:p-10">
        <p className="flex items-center gap-2 text-[0.9375rem] font-semibold tracking-tight">
          <span className="logo-note" aria-hidden />
          Prins
        </p>

        <div className="mx-auto flex w-full max-w-sm flex-col gap-8">
          <p className="text-lg leading-snug font-medium tracking-[-0.02em] text-balance lg:hidden">
            {PITCH}
          </p>
          <form onSubmit={submit} noValidate className="rise-in flex flex-col gap-5">
            <h1 className="text-3xl font-medium tracking-[-0.03em]">
              {mode === "in" ? "Welcome back" : "Create your account"}
            </h1>
            {mode === "up" ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="name">Name</Label>
                <Input id="name" name="name" autoComplete="name" />
              </div>
            ) : null}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" name="email" type="email" autoComplete="email" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
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
            <Button type="submit" disabled={busy} className="h-12 text-[0.9375rem]">
              {busy ? "One moment..." : mode === "in" ? "Sign in" : "Create account"}
            </Button>
            {signUpAllowed ? (
              <button
                type="button"
                className="cursor-pointer text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
                onClick={() => {
                  setMode(mode === "in" ? "up" : "in");
                  setError(null);
                }}
              >
                {mode === "in" ? "Need an account? Create one" : "Already have an account? Sign in"}
              </button>
            ) : null}
          </form>
        </div>

        <a
          href="/demo"
          className="group flex w-fit items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          See the concept model
          <ArrowUpRight
            className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
            aria-hidden
          />
        </a>
      </div>

      <aside className="on-brand relative isolate hidden flex-col justify-end gap-10 overflow-hidden bg-brand p-12 text-brand-foreground lg:flex">
        <Halftone
          fade="top"
          pitch={11}
          interactive
          alwaysDark
          opacity={0.4}
          className="absolute inset-0 -z-10 size-full text-white"
        />
        <NotePaper item={SAMPLE} className="note-feed mx-auto w-full max-w-md -rotate-2" />
        <p className="rise-in max-w-xl text-3xl leading-[1.12] font-medium tracking-[-0.03em] text-balance xl:text-4xl">
          {PITCH}
        </p>
      </aside>
    </main>
  );
}
