import { sqliteTable, integer, text, real, index } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { conversations } from "./conversations";

export const memoryItems = sqliteTable(
  "memory_items",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    conversationId: text("conversation_id", { length: 128 })
      .notNull()
      .references(() => conversations.id),
    content: text("content").notNull(),
    type: text("type", { length: 64 }).notNull(),
    topicKey: text("topic_key", { length: 128 }).notNull().default(""),
    confidence: real("confidence").notNull().default(0.0),
    importance: real("importance").notNull().default(0.0),
    stability: real("stability").notNull().default(0.0),
    freshness: real("freshness").notNull().default(0.0),
    informationGain: real("information_gain").notNull().default(0.0),
    sourceMessageIdsJson: text("source_message_ids_json").notNull().default("[]"),
    status: text("status", { length: 32 }).notNull().default("active"),
    version: integer("version").notNull().default(1),
    createdAt: text("created_at")
      .notNull()
      .default(sql`(CURRENT_TIMESTAMP)`),
    updatedAt: text("updated_at")
      .notNull()
      .default(sql`(CURRENT_TIMESTAMP)`),
  },
  (table) => [
    index("idx_memory_items_conversation_id").on(table.conversationId),
    index("idx_memory_items_type").on(table.type),
    index("idx_memory_items_topic_key").on(table.topicKey),
    index("idx_memory_items_status").on(table.status),
  ]
);

export type MemoryItem = typeof memoryItems.$inferSelect;
export type NewMemoryItem = typeof memoryItems.$inferInsert;
