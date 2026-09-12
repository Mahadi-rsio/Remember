import { pgTable, varchar, text, timestamp, index } from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

export const conversations = pgTable(
  "conversations",
  {
    id: varchar("id", { length: 128 }).primaryKey(),
    userKey: varchar("user_key", { length: 128 }),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "string" })
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "string" })
      .notNull()
      .default(sql`now()`),
    metadataJson: text("metadata_json"),
  },
  (table) => [
    index("idx_conversations_user_key").on(table.userKey),
  ]
);

export type Conversation = typeof conversations.$inferSelect;
export type NewConversation = typeof conversations.$inferInsert;
