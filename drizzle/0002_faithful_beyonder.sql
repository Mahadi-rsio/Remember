ALTER TABLE "memory_items" ADD COLUMN "supersedes_id" integer;--> statement-breakpoint
ALTER TABLE "memory_items" ADD COLUMN "contradicts_ids_json" text DEFAULT '[]' NOT NULL;--> statement-breakpoint
ALTER TABLE "memory_items" ADD COLUMN "related_memory_ids_json" text DEFAULT '[]' NOT NULL;--> statement-breakpoint
ALTER TABLE "memory_items" ADD COLUMN "relationship" varchar(32);--> statement-breakpoint
CREATE INDEX "idx_memory_items_supersedes_id" ON "memory_items" USING btree ("supersedes_id");