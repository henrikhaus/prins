/**
 * Creates a demo account with made-up data, for showing the dashboard to customers.
 * The dashboard labels this data as a sample. Only ever touches the demo account.
 *
 *   DEMO_PASSWORD=... bun run seed
 */
process.env.ALLOW_SIGNUP = "true";

export {};

const { randomBytes } = await import("node:crypto");
const { eq } = await import("drizzle-orm");
const { auth } = await import("../src/server/auth.server");
const { db } = await import("../src/server/db.server");
const { devices, friendships, items, printPermissions, user } =
  await import("../src/server/schema");
const { newDeviceToken } = await import("../src/server/sync.server");

const DEMO_EMAIL = process.env.DEMO_EMAIL ?? "demo@prins.henhau.no";
const password = process.env.DEMO_PASSWORD ?? randomBytes(12).toString("base64url");
const DAY_MS = 86_400_000;

// A small fixed-seed generator, so every run produces the same demo.
let state = 20261105;
const random = () => {
  state = (state * 1664525 + 1013904223) % 4294967296;
  return state / 4294967296;
};
const pick = <T>(list: readonly T[]) => list[Math.floor(random() * list.length)];

const SENDERS = {
  slack: ["Maria", "Jonas", "Ingrid", "Sam", "Aisha"],
  email: [
    "Lena at Northwind",
    "Tom at Fjordline Freight",
    "Accounts at Halden Print",
    "Priya at Kvist Studio",
  ],
  voice: [""],
  agent: ["Build agent"],
  friend: ["Sam"],
} as const;

const TASKS = [
  ["Send the Q3 numbers to the board", "Churn and net revenue on one slide."],
  ["Review the pricing page copy", "Comments are in the shared doc."],
  ["Approve the print invoice", "Due at the end of the week."],
  ["Reply about the contract renewal", "They need an answer before their board meets."],
  ["Book a room for the design review", ""],
  ["Call the accountant about the VAT return", ""],
  ["Decide on the database migration", "The build agent is blocked until you approve."],
  ["Give Jonas feedback on the hiring plan", ""],
  ["Update the investor list", "Add the two intros from last week."],
  ["Order more label rolls", ""],
] as const;

const NOISE = [
  "Weekly newsletter",
  "Lunch is at noon",
  "Build passed on main",
  "Thanks, got it!",
  "Calendar update",
];

const existing = db.select().from(user).where(eq(user.email, DEMO_EMAIL)).get();
if (existing) db.delete(user).where(eq(user.id, existing.id)).run();

const created = await auth.api.signUpEmail({ body: { name: "Demo", email: DEMO_EMAIL, password } });

const device = db
  .insert(devices)
  .values({
    userId: created.user.id,
    name: "Demo desk",
    tokenHash: newDeviceToken().tokenHash,
    isDemo: true,
    lastSeenAt: new Date(),
    status: {
      deviceKind: "atech",
      printer: "atech",
      handyInstalled: true,
      slack: true,
      email: true,
      mode: "idle",
      queue: 3,
      version: "0.1.0",
    },
  })
  .returning()
  .get();

const now = Date.now();
let localId = 0;
const add = (values: {
  source: keyof typeof SENDERS;
  sender?: string;
  title: string;
  detail?: string;
  status: "queued" | "printed" | "dismissed" | "ignored";
  ageMs: number;
  priority?: "high" | "normal" | "low";
  due?: string;
  bitmap?: string;
}) => {
  localId += 1;
  const createdAt = new Date(now - values.ageMs);
  db.insert(items)
    .values({
      deviceId: device.id,
      localId,
      source: values.source,
      sender: values.sender ?? pick(SENDERS[values.source]),
      title: values.title,
      detail: values.detail ?? "",
      priority: values.priority ?? "normal",
      due: values.due ?? "",
      status: values.status,
      engine: "model",
      bitmap: values.bitmap ?? null,
      createdAt,
      decidedAt: values.status === "queued" ? null : new Date(createdAt.getTime() + 3_600_000),
    })
    .run();
};

for (let day = 13; day >= 0; day--) {
  const weekend = [0, 6].includes(new Date(now - day * DAY_MS).getDay());
  const messages = weekend ? 2 + Math.floor(random() * 4) : 14 + Math.floor(random() * 14);
  for (let index = 0; index < messages; index++) {
    const ageMs = day * DAY_MS + (index + 1) * 900_000;
    const roll = random();
    const source = pick(["slack", "slack", "slack", "email", "email", "voice", "agent"] as const);
    if (roll < 0.72) {
      add({
        source: source === "voice" ? "email" : source,
        title: pick(NOISE),
        status: "ignored",
        ageMs,
      });
    } else {
      const [title, detail] = pick(TASKS);
      add({ source, title, detail, status: roll < 0.9 ? "printed" : "dismissed", ageMs });
    }
  }
}

add({
  source: "slack",
  sender: "Maria",
  title: "Send the Q3 numbers to Maria",
  detail: "Churn and net revenue on one slide.",
  status: "queued",
  ageMs: 600_000,
  priority: "high",
  due: "before Friday's board call",
});
add({
  source: "email",
  sender: "Lena at Northwind",
  title: "Reply to Northwind about the renewal",
  detail: "They need an answer before their board meets.",
  status: "queued",
  ageMs: 1_800_000,
});
add({
  source: "voice",
  title: "Book the dentist",
  detail: "Before the end of the month.",
  status: "queued",
  ageMs: 3_000_000,
});

// A note from a friend, in a design made by the real engine: scripts/demo-note.b64.
const design = (await Bun.file(new URL("./demo-note.b64", import.meta.url)).text()).trim();
add({
  source: "friend",
  sender: "Sam",
  title: "Happy birthday!",
  status: "queued",
  ageMs: 300_000,
  bitmap: design,
});

const person = async (name: string, email: string) => {
  const old = db.select().from(user).where(eq(user.email, email)).get();
  if (old) db.delete(user).where(eq(user.id, old.id)).run();
  const made = await auth.api.signUpEmail({
    body: { name, email, password: randomBytes(24).toString("base64url") },
  });
  return made.user.id;
};
const demoId = created.user.id;
const samId = await person("Sam", "sam@demo.prins.invalid");
const ingridId = await person("Ingrid", "ingrid@demo.prins.invalid");
db.insert(friendships)
  .values({ requesterId: samId, addresseeId: demoId, status: "accepted" })
  .run();
db.insert(printPermissions)
  .values([
    { grantorId: demoId, granteeId: samId },
    { grantorId: samId, granteeId: demoId },
  ])
  .run();
db.insert(friendships)
  .values({ requesterId: ingridId, addresseeId: demoId, status: "pending" })
  .run();

console.log(`Demo account ready: ${DEMO_EMAIL}`);
if (!process.env.DEMO_PASSWORD) console.log(`Password: ${password}`);
process.exit(0);
