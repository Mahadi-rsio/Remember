import { defineConfig } from "drizzle-kit";
import * as dotenv from "dotenv";

// Load local environment variables from .dev.vars or .env
dotenv.config({ path: ".dev.vars" });
dotenv.config();

export default defineConfig({
  schema: "./src/db/schema/index.ts",
  out: "./drizzle",
  dialect: "turso",
  dbCredentials: {
    url: process.env.TURSO_DATABASE_URL ?? "file:./local.db",
    authToken: process.env.TURSO_AUTH_TOKEN,
  },
});
