import { sqliteTable, integer, text, index, uniqueIndex } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { conversations } from "./conversations";

export const contextVersions = sqliteTable(
  "context_versions",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    conversationId: text("conversation_id", { length: 128 })
      .notNull()
      .references(() => conversations.id),
    version: integer("version").notNull().default(1),
    stateJson: text("state_json").notNull().default("{}"),
    sourceMessageIdsJson: text("source_message_ids_json").notNull().default("[]"),
    createdAt: text("created_at")
      .notNull()
      .default(sql`(CURRENT_TIMESTAMP)`),
  },
  (table) => [
    index("idx_context_versions_conversation_id").on(table.conversationId),
    uniqueIndex("uq_conv_context_version").on(table.conversationId, table.version),
  ]
);

export type ContextVersion = typeof contextVersions.$inferSelect;
export type NewContextVersion = typeof contextVersions.$inferInsert;
