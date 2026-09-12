import { pgTable, varchar, text, timestamp, serial, integer, index, uniqueIndex } from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";
import { conversations } from "./conversations";

export const contextVersions = pgTable(
  "context_versions",
  {
    id: serial("id").primaryKey(),
    conversationId: varchar("conversation_id", { length: 128 })
      .notNull()
      .references(() => conversations.id),
    version: integer("version").notNull().default(1),
    stateJson: text("state_json").notNull().default("{}"),
    sourceMessageIdsJson: text("source_message_ids_json").notNull().default("[]"),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "string" })
      .notNull()
      .default(sql`now()`),
  },
  (table) => [
    index("idx_context_versions_conversation_id").on(table.conversationId),
    uniqueIndex("uq_conv_context_version").on(table.conversationId, table.version),
  ]
);

export type ContextVersion = typeof contextVersions.$inferSelect;
export type NewContextVersion = typeof contextVersions.$inferInsert;
