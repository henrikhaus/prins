# Prins dashboard

The web side of Prins: see the queue, print or dismiss from anywhere, browse history, and connect devices. The daemon on the Mac syncs to it every 5 seconds. The device keeps working if the dashboard is down.

**Stack:** Bun, TanStack Start, Zod, Oxc, SQLite, Drizzle, BetterAuth, Tailwind, shadcn with Base UI.

**Needs Bun 1.4.4 or newer.** Bun 1.3.9 fails to parse the production bundle and every page returns a 500. Run `bun upgrade`.

## Run it locally

```sh
bun install
bun run dev        # http://localhost:3000
```

For a first account, start it with `ALLOW_SIGNUP=true bun run dev`.

To see it with data but no device:

```sh
DEMO_PASSWORD=choose-one bun run seed
```

Then sign in as `demo@prins.henhau.no`. The numbers are made up, and nothing on the page says so now, so say it yourself when you show it.

## Friends

Each person has a friend code. Add someone with theirs, and they accept. Being friends lets neither of you print: each person ticks who may send notes to their own Prins.

Notes come from the Friends page, where you can write or draw, or from an agent through the MCP server's `send_to_friend`. They always wait for the recipient's button, and the screen shows the design first. Taking permission back also stops notes that haven't been delivered yet.

## Connect a device

1. In the dashboard, go to **Devices**, then **Add device**. The token is only shown once.
2. Put the two lines it gives you in the `.env` next to the daemon:

   ```sh
   PRINS_CLOUD_URL=https://prins.henhau.no
   PRINS_CLOUD_TOKEN=prins_...
   ```

3. Restart `prins run`.

**What gets uploaded:** the short note, source, sender, timestamps, device status, and the picture for a custom design. The raw message text and audio stay on the Mac. Tokens are stored hashed.

## Deploy on Dokploy

1. **Application:** create one from the GitHub repo. Set the build type to Dockerfile and the build path to `dashboard`. The repo is private, so Dokploy needs access through its GitHub provider.
2. **Volume:** mount a volume at `/data`. Without it, the database is lost on every deploy.
3. **Environment:**

   ```sh
   BETTER_AUTH_SECRET=     # openssl rand -base64 32
   BETTER_AUTH_URL=https://prins.henhau.no
   ALLOW_SIGNUP=true       # Only until your account exists
   ```

4. **Domain:** `prins.henhau.no`, container port `3000`, HTTPS on.
5. **DNS at Domeneshop:** `prins.henhau.no` must point to the server. Check that it does before deploying.
6. **Lock it down:** create your account, then set `ALLOW_SIGNUP=false` and redeploy. Otherwise anyone can register.

For a customer demo, run this in the container's terminal:

```sh
DEMO_PASSWORD=choose-one bun run seed
```

**Backups:** SQLite is one file on that volume, so nothing backs it up unless you set that up.

## Checks

```sh
bun run check      # oxlint, oxfmt, tsc, tests
```

## Public demo

`/demo` shows the 3D model full screen with no login, to send to potential customers: https://prins.henhau.no/demo. It only shows the concept model. It's labelled as a concept design, so keep it that way until the real thing matches.

The page is built from `demo/product-3d/src`: `atmosphere.js` draws the light and `main.js` is the model. Run `node demo/product-3d/src/build.mjs <tools dir>`, where the tools dir has `three@0.187.0`, `esbuild` and `@fontsource/archivo` installed. Then copy `demo/product-3d/index.html` to `public/demo/product-3d.html`. The light and text effects are adapted from [React Bits](https://reactbits.dev) under its MIT + Commons Clause license, so we can use them in the product but can't sell or redistribute them as components.

## Design

Warm brown (`#704A34`) and sand, with notes always black on paper. The desk is home: one note at a time, and a decision waits 5 seconds before it reaches the server, so it can be undone. Effects are adapted from React Bits (PatternWaves, CountUp, PillNav, Stack), under the same license as above. All motion respects reduced-motion.

## Presentation

`/presentation` is a five-slide deck with the live 3D model, public like `/demo`. Use the arrow keys or click to move, and press F for full screen.

## Temporary

The **3D model** page (account menu, or a link on Devices) shows the concept render for demos. `public/demo/product-3d.html` is a copy of `demo/product-3d/index.html`. To remove it, delete `src/routes/_app/product.tsx`, its entry in `src/components/app-shell.tsx`, and `public/demo/`.

## Worth knowing

- **Dates go through `src/lib/format.ts`.** Don't call `toLocaleString` or `Intl...format()` in a component. Bun and Chrome format dates differently, and any difference between the server's HTML and the browser's render makes React discard the page.
- **Server functions use `.validator()`,** not `.inputValidator()`, in this TanStack Start version.
- **Every query filters by the signed-in user's devices.** Tests in `tests/sync.test.ts` check that accounts stay apart. Keep them passing.
- **One time zone, `Europe/Oslo`,** decides which day a message counts towards. It'll need to become per-user once customers are elsewhere.
- **The Vercel AI SDK isn't used,** because the model runs in the daemon. Add it when the dashboard needs its own AI feature.
