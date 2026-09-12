import { pgTable, varchar, text, timestamp, serial, integer, index, uniqueIndex } from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";
import { conversations } from "./conversations";

export const messages = pgTable(
  "messages",
  {
    id: serial("id").primaryKey(),
    conversationId: varchar("conversation_id", { length: 128 })
      .notNull()
      .references(() => conversations.id),
    messageKey: varchar("message_key", { length: 128 }).notNull(),
    role: varchar("role", { length: 32 }).notNull(),
    content: text("content").notNull(),
    contentHash: varchar("content_hash", { length: 64 }).notNull(),
    ordinal: integer("ordinal").notNull().default(0),
    clientMessageId: varchar("client_message_id", { length: 128 }),
    metadataJson: text("metadata_json"),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "string" })
      .notNull()
      .default(sql`now()`),
  },
  (table) => [
    index("idx_messages_conversation_id").on(table.conversationId),
    index("idx_messages_message_key").on(table.messageKey),
    uniqueIndex("uq_conv_message_key").on(table.conversationId, table.messageKey),
  ]
);

export type Message = typeof messages.$inferSelect;
export type NewMessage = typeof messages.$inferInsert;
