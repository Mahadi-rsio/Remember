import { sqliteTable, integer, text, index, uniqueIndex } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { conversations } from "./conversations";

export const messages = sqliteTable(
  "messages",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    conversationId: text("conversation_id", { length: 128 })
      .notNull()
      .references(() => conversations.id),
    messageKey: text("message_key", { length: 128 }).notNull(),
    role: text("role", { length: 32 }).notNull(),
    content: text("content").notNull(),
    contentHash: text("content_hash", { length: 64 }).notNull(),
    ordinal: integer("ordinal").notNull().default(0),
    clientMessageId: text("client_message_id", { length: 128 }),
    metadataJson: text("metadata_json"),
    createdAt: text("created_at")
      .notNull()
      .default(sql`(CURRENT_TIMESTAMP)`),
  },
  (table) => [
    index("idx_messages_conversation_id").on(table.conversationId),
    index("idx_messages_message_key").on(table.messageKey),
    uniqueIndex("uq_conv_message_key").on(table.conversationId, table.messageKey),
  ]
);

export type Message = typeof messages.$inferSelect;
export type NewMessage = typeof messages.$inferInsert;
