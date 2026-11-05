import { Link, useRouter } from "@tanstack/react-router";
import { Box, Cpu, History, Inbox, LayoutDashboard, LogOut, Users } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, exact: true },
  { to: "/queue", label: "Queue", icon: Inbox, exact: false },
  { to: "/history", label: "History", icon: History, exact: false },
  { to: "/friends", label: "Friends", icon: Users, exact: false },
  { to: "/devices", label: "Devices", icon: Cpu, exact: false },
  // Temporary, for showing customers the product.
  { to: "/product", label: "3D model", icon: Box, exact: false },
] as const;

export function AppShell({ email, children }: { email: string; children: ReactNode }) {
  const router = useRouter();
  const signOut = async () => {
    await authClient.signOut();
    await router.navigate({ to: "/login" });
  };

  return (
    <div className="min-h-svh md:grid md:grid-cols-[13rem_1fr]">
      <aside className="flex flex-col gap-3 border-b bg-sidebar p-4 md:sticky md:top-0 md:h-svh md:border-r md:border-b-0">
        <div className="flex items-center justify-between md:mb-4">
          <Link to="/" className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <span className="logo-note" aria-hidden />
            Prins
          </Link>
          <Button variant="ghost" size="sm" className="md:hidden" onClick={signOut}>
            <LogOut aria-hidden />
            Sign out
          </Button>
        </div>
        <nav
          className="-mx-1 flex gap-1 overflow-x-auto md:flex-col md:overflow-visible"
          aria-label="Main"
        >
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              activeOptions={{ exact: item.exact }}
              className="flex shrink-0 items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
              activeProps={{ className: "bg-sidebar-accent font-medium !text-foreground" }}
            >
              <item.icon className="hidden size-4 md:block" aria-hidden />
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto hidden flex-col gap-2 md:flex">
          <p className="truncate px-2.5 text-xs text-muted-foreground">{email}</p>
          <Button variant="ghost" size="sm" className="justify-start" onClick={signOut}>
            <LogOut aria-hidden />
            Sign out
          </Button>
        </div>
      </aside>
      <main className="min-w-0 px-4 py-6 md:px-8 md:py-8">
        <div className="mx-auto flex max-w-5xl flex-col gap-6">{children}</div>
      </main>
    </div>
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <header>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
    </header>
  );
}

export function Panel({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border bg-card p-4 md:p-5 ${className}`}>
      {title ? <h2 className="mb-4 text-sm font-medium">{title}</h2> : null}
      {children}
    </section>
  );
}
