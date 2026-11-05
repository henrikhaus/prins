import { HeadContent, Link, Scripts, createRootRoute } from "@tanstack/react-router";
import type { ReactNode } from "react";

import appCss from "../styles.css?url";

// Runs before paint so a dark-mode reader never sees a light flash.
const THEME_SCRIPT = `document.documentElement.classList.toggle("dark", matchMedia("(prefers-color-scheme: dark)").matches)`;

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Prins" },
      {
        name: "description",
        content: "Your inbox and your voice, turned into sticky notes you approve with a button.",
      },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: "/favicon.svg", type: "image/svg+xml" },
    ],
    scripts: [{ children: THEME_SCRIPT }],
  }),
  notFoundComponent: () => (
    <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center gap-2 p-6">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="text-sm underline">
        Back to the overview
      </Link>
    </main>
  ),
  shellComponent: RootDocument,
});

function RootDocument({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}
