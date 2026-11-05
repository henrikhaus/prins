import { Menu } from "@base-ui/react/menu";
import { Link, useRouter, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  Box,
  Keyboard,
  LogOut,
  Monitor,
  Presentation,
  Moon,
  PanelsTopLeft,
  Settings,
  Sun,
  Users,
} from "lucide-react";
import { createContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import type { DeviceRow } from "@/components/device-status";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { authClient } from "@/lib/auth-client";

const NAV = [
  { to: "/", label: "Desk", icon: PanelsTopLeft },
  { to: "/activity", label: "Activity", icon: Activity },
  { to: "/friends", label: "Friends", icon: Users },
  { to: "/devices", label: "Devices", icon: Box },
] as const;

type Theme = "system" | "light" | "dark";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

function activeIndex(pathname: string) {
  const index = NAV.findIndex((item) =>
    item.to === "/" ? pathname === "/" : pathname.startsWith(item.to),
  );
  return index;
}

function Count({ value, inverted = false }: { value: number; inverted?: boolean }) {
  if (value === 0) return null;
  return (
    <span
      className={`ml-1.5 inline-flex min-w-4.5 items-center justify-center rounded-full px-1 font-mono text-[0.6875rem] leading-[1.125rem] tabular-nums ${
        inverted ? "bg-primary-foreground text-primary" : "bg-hot text-hot-foreground"
      }`}
    >
      {value}
    </span>
  );
}

/** The sliding pill is adapted from React Bits (PillNav), MIT + Commons Clause, (c) 2026 David Haz. */
function PillNav({ counts }: { counts: Record<string, number> }) {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const active = activeIndex(pathname);
  const links = useRef<(HTMLAnchorElement | null)[]>([]);
  const [pill, setPill] = useState<{ left: number; width: number } | null>(null);

  useIsoLayoutEffect(() => {
    const measure = () => {
      const link = links.current[active];
      setPill(link ? { left: link.offsetLeft, width: link.offsetWidth } : null);
    };
    measure();
    void document.fonts?.ready.then(measure);
  }, [active, counts]);

  return (
    <nav
      aria-label="Main"
      className="relative hidden items-center gap-0.5 rounded-full border bg-card/70 p-1 md:flex"
    >
      {pill ? (
        <span
          aria-hidden
          className="absolute top-1 bottom-1 rounded-full bg-primary transition-[left,width] duration-400 ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={{ left: pill.left, width: pill.width }}
        />
      ) : null}
      {NAV.map((item, index) => (
        <Link
          key={item.to}
          to={item.to}
          viewTransition
          ref={(element) => {
            links.current[index] = element;
          }}
          aria-current={index === active ? "page" : undefined}
          className={`relative flex h-8 items-center rounded-full px-3.5 text-[0.8125rem] font-medium transition-colors duration-200 ${
            index === active
              ? "text-primary-foreground"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {item.label}
          <Count value={counts[item.to] ?? 0} inverted={index === active} />
        </Link>
      ))}
    </nav>
  );
}

function BottomTabs({ counts }: { counts: Record<string, number> }) {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const active = activeIndex(pathname);
  return (
    <nav
      aria-label="Main"
      className="shell-tabs fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t bg-background/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden"
    >
      {NAV.map((item, index) => (
        <Link
          key={item.to}
          to={item.to}
          viewTransition
          aria-current={index === active ? "page" : undefined}
          className={`relative flex h-14 flex-col items-center justify-center gap-0.5 text-[0.6875rem] font-medium ${
            index === active ? "text-primary" : "text-muted-foreground"
          }`}
        >
          <item.icon className="size-5" strokeWidth={index === active ? 2.2 : 1.6} aria-hidden />
          {item.label}
          {counts[item.to] ? (
            <span className="absolute top-1.5 left-1/2 ml-2 min-w-4 rounded-full bg-hot px-1 text-center font-mono text-[0.625rem] leading-4 text-hot-foreground tabular-nums">
              {counts[item.to]}
            </span>
          ) : null}
        </Link>
      ))}
    </nav>
  );
}

function useTheme() {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("prins-theme");
      if (saved === "light" || saved === "dark") setTheme(saved);
    } catch {
      // Private browsing: the system setting still applies.
    }
  }, []);
  const choose = (next: Theme) => {
    setTheme(next);
    try {
      if (next === "system") localStorage.removeItem("prins-theme");
      else localStorage.setItem("prins-theme", next);
    } catch {
      // It just won't be remembered.
    }
    const dark =
      next === "dark" || (next === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  };
  return [theme, choose] as const;
}

const THEMES = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
] as const;

export function ThemeChoice() {
  const [theme, setTheme] = useTheme();
  return (
    <div role="radiogroup" aria-label="Theme" className="flex rounded-full bg-muted p-0.5">
      {THEMES.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={theme === option.value}
          aria-label={option.label}
          title={option.label}
          onClick={() => setTheme(option.value)}
          className={`flex size-7 cursor-pointer items-center justify-center rounded-full transition-colors ${
            theme === option.value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <option.icon className="size-3.5" aria-hidden />
        </button>
      ))}
    </div>
  );
}

const itemClass =
  "flex h-9 cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm outline-none data-[highlighted]:bg-accent [&_svg]:size-4 [&_svg]:text-muted-foreground";

function AccountMenu({
  email,
  name,
  onShortcuts,
}: {
  email: string;
  name: string;
  onShortcuts: () => void;
}) {
  const router = useRouter();
  const signOut = async () => {
    await authClient.signOut();
    await router.navigate({ to: "/login" });
  };
  return (
    <Menu.Root>
      <Menu.Trigger
        aria-label="Account and settings"
        className="flex size-9 cursor-pointer items-center justify-center rounded-full border bg-card/70 text-[0.8125rem] font-medium uppercase transition-colors hover:bg-accent"
      >
        {(name || email).charAt(0)}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner sideOffset={8} align="end" className="z-50">
          <Menu.Popup className="w-64 origin-(--transform-origin) rounded-2xl border bg-popover p-1.5 text-popover-foreground shadow-xl outline-none transition-[transform,opacity] duration-150 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0">
            <div className="px-2.5 py-2">
              <p className="truncate text-sm font-medium">{name || "Your account"}</p>
              <p className="truncate text-xs text-muted-foreground">{email}</p>
            </div>
            <div className="my-1 h-px bg-border" />
            <div className="flex items-center justify-between gap-2 px-2.5 py-1.5">
              <span className="text-sm">Theme</span>
              <ThemeChoice />
            </div>
            <div className="my-1 h-px bg-border" />
            <Menu.Item
              className={itemClass}
              onClick={() => void router.navigate({ to: "/settings" })}
            >
              <Settings aria-hidden />
              Settings
            </Menu.Item>
            <Menu.Item className={itemClass} onClick={onShortcuts}>
              <Keyboard aria-hidden />
              Keyboard shortcuts
              <span className="kbd ml-auto">?</span>
            </Menu.Item>
            <Menu.Item
              className={itemClass}
              onClick={() => void router.navigate({ to: "/presentation" })}
            >
              <Presentation aria-hidden />
              Presentation
            </Menu.Item>
            <Menu.Item
              className={itemClass}
              onClick={() => void router.navigate({ to: "/product" })}
            >
              <Box aria-hidden />
              3D model
            </Menu.Item>
            <div className="my-1 h-px bg-border" />
            <Menu.Item className={itemClass} onClick={signOut}>
              <LogOut aria-hidden />
              Sign out
            </Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

const SHORTCUTS = [
  ["P", "Print the note in front"],
  ["D", "Dismiss the note in front"],
  ["Z", "Undo, for 5 seconds after a decision"],
  ["J / K", "Next or previous note"],
  ["?", "Show this list"],
] as const;

export function isTyping(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
}

function ShortcutsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            On your desk, you can decide without touching the mouse.
          </DialogDescription>
        </DialogHeader>
        <dl className="flex flex-col divide-y">
          {SHORTCUTS.map(([key, label]) => (
            <div key={key} className="flex items-center justify-between gap-4 py-2.5 text-sm">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-mono text-xs">{key}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}

/** The desk tells the frame which notes are on their way out, so both counts agree. */
export const HiddenNotes = createContext<(ids: ReadonlySet<number>) => void>(() => {});

export function AppShell({
  email,
  name,
  devices,
  waitingIds,
  requests,
  children,
}: {
  email: string;
  name: string;
  devices: DeviceRow[];
  waitingIds: number[];
  requests: number;
  children: ReactNode;
}) {
  const [shortcuts, setShortcuts] = useState(false);
  const [hidden, setHidden] = useState<ReadonlySet<number>>(new Set());
  const waiting = useMemo(
    () => waitingIds.filter((id) => !hidden.has(id)).length,
    [waitingIds, hidden],
  );
  const counts: Record<string, number> = { "/": waiting, "/friends": requests };
  const device = devices.find((candidate) => candidate.online) ?? devices[0];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "?" && !isTyping(event.target)) setShortcuts((open) => !open);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex min-h-svh flex-col">
      <header className="shell-top sticky top-0 z-30 grid grid-cols-[1fr_auto] items-center gap-3 bg-background/80 px-4 py-3 backdrop-blur-xl md:grid-cols-[1fr_auto_1fr] md:px-6">
        <Link
          to="/"
          className="flex w-fit items-center gap-2 text-[0.9375rem] font-semibold tracking-tight"
        >
          <span className="logo-note" aria-hidden />
          Prins
        </Link>
        <PillNav counts={counts} />
        <div className="flex items-center justify-end gap-2">
          {device ? (
            <Link
              to="/devices"
              className="flex h-9 max-w-44 items-center gap-2 rounded-full border bg-card/70 px-3 text-[0.8125rem] transition-colors hover:bg-accent"
              title={device.online ? `${device.name} is online` : `${device.name} is offline`}
            >
              <span className="live-dot" data-online={device.online} aria-hidden />
              <span className="truncate">{device.name}</span>
              <span className="sr-only">{device.online ? "online" : "offline"}</span>
            </Link>
          ) : null}
          <AccountMenu email={email} name={name} onShortcuts={() => setShortcuts(true)} />
        </div>
      </header>

      <main className="flex min-w-0 flex-1 flex-col overflow-x-clip px-4 pt-4 pb-24 md:px-8 md:pt-8 md:pb-16">
        <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10">
          <HiddenNotes.Provider value={setHidden}>{children}</HiddenNotes.Provider>
        </div>
      </main>

      <BottomTabs counts={counts} />
      <ShortcutsDialog open={shortcuts} onOpenChange={setShortcuts} />
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="rise-in flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-medium tracking-[-0.03em] md:text-4xl">{title}</h1>
        {description ? (
          <p className="mt-2 text-[0.9375rem] text-pretty text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action}
    </header>
  );
}

/** A titled block of the page: a hairline and a small label, not a box. */
export function Section({
  title,
  aside,
  children,
  className = "",
}: {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rise-in border-t pt-4 ${className}`}>
      {title || aside ? (
        <div className="mb-5 flex items-center justify-between gap-3">
          {title ? <h2 className="eyebrow">{title}</h2> : <span />}
          {aside}
        </div>
      ) : null}
      {children}
    </section>
  );
}
