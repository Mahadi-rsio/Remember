import { sqliteTable, text, index } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";

export const conversations = sqliteTable(
  "conversations",
  {
    id: text("id", { length: 128 }).primaryKey(),
    userKey: text("user_key", { length: 128 }),
    createdAt: text("created_at")
      .notNull()
      .default(sql`(CURRENT_TIMESTAMP)`),
    updatedAt: text("updated_at")
      .notNull()
      .default(sql`(CURRENT_TIMESTAMP)`),
    metadataJson: text("metadata_json"),
  },
  (table) => [
    index("idx_conversations_user_key").on(table.userKey),
  ]
);

export type Conversation = typeof conversations.$inferSelect;
export type NewConversation = typeof conversations.$inferInsert;
