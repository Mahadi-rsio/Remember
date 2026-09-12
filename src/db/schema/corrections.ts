import { sqliteTable, integer, text, index } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { conversations } from "./conversations";

export const corrections = sqliteTable(
  "corrections",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    conversationId: text("conversation_id", { length: 128 })
      .notNull()
      .references(() => conversations.id),
    target: text("target", { length: 256 }).notNull().default(""),
    oldValue: text("old_value", { length: 1024 }).notNull().default(""),
    newValue: text("new_value", { length: 1024 }).notNull().default(""),
    status: text("status", { length: 32 }).notNull().default("active"),
    sourceMessageIdsJson: text("source_message_ids_json").notNull().default("[]"),
    createdAt: text("created_at")
      .notNull()
      .default(sql`(CURRENT_TIMESTAMP)`),
  },
  (table) => [
    index("idx_corrections_conversation_id").on(table.conversationId),
  ]
);

export type Correction = typeof corrections.$inferSelect;
export type NewCorrection = typeof corrections.$inferInsert;
