ALTER TABLE "memory_items" ADD COLUMN "subject" varchar(256) DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE "memory_items" ADD COLUMN "predicate" varchar(256) DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE "memory_items" ADD COLUMN "value" text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE "memory_items" ADD COLUMN "scope" varchar(32) DEFAULT 'project' NOT NULL;--> statement-breakpoint
ALTER TABLE "memory_items" ADD COLUMN "valid_from" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "memory_items" ADD COLUMN "valid_until" timestamp with time zone;--> statement-breakpoint
CREATE INDEX "idx_memory_items_subject" ON "memory_items" USING btree ("subject");--> statement-breakpoint
CREATE INDEX "idx_memory_items_predicate" ON "memory_items" USING btree ("predicate");--> statement-breakpoint
CREATE INDEX "idx_memory_items_scope" ON "memory_items" USING btree ("scope");