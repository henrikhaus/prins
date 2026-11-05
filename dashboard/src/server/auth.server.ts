import { drizzleAdapter } from "@better-auth/drizzle-adapter";
import { betterAuth } from "better-auth";
import { tanstackStartCookies } from "better-auth/tanstack-start";

import { db } from "./db.server";
import * as schema from "./schema";

const isProduction = process.env.NODE_ENV === "production";

if (isProduction && !process.env.BETTER_AUTH_SECRET) {
  throw new Error("BETTER_AUTH_SECRET must be set in production.");
}

/** Closed unless asked for: the dashboard is on the public internet. */
export const signUpAllowed = () => process.env.ALLOW_SIGNUP === "true";

export const auth = betterAuth({
  database: drizzleAdapter(db, { provider: "sqlite", schema }),
  secret: process.env.BETTER_AUTH_SECRET ?? "development-only-secret-do-not-use-in-production",
  baseURL: process.env.BETTER_AUTH_URL ?? "http://localhost:3000",
  emailAndPassword: {
    enabled: true,
    minPasswordLength: 10,
    disableSignUp: !signUpAllowed(),
  },
  // Must be the last plugin.
  plugins: [tanstackStartCookies()],
});
