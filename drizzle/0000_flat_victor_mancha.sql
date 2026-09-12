CREATE TABLE "conversations" (
	"id" varchar(128) PRIMARY KEY NOT NULL,
	"user_key" varchar(128),
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"metadata_json" text
);
--> statement-breakpoint
CREATE TABLE "messages" (
	"id" serial PRIMARY KEY NOT NULL,
	"conversation_id" varchar(128) NOT NULL,
	"message_key" varchar(128) NOT NULL,
	"role" varchar(32) NOT NULL,
	"content" text NOT NULL,
	"content_hash" varchar(64) NOT NULL,
	"ordinal" integer DEFAULT 0 NOT NULL,
	"client_message_id" varchar(128),
	"metadata_json" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "memory_items" (
	"id" serial PRIMARY KEY NOT NULL,
	"conversation_id" varchar(128) NOT NULL,
	"content" text NOT NULL,
	"type" varchar(64) NOT NULL,
	"topic_key" varchar(128) DEFAULT '' NOT NULL,
	"confidence" real DEFAULT 0 NOT NULL,
	"importance" real DEFAULT 0 NOT NULL,
	"stability" real DEFAULT 0 NOT NULL,
	"freshness" real DEFAULT 0 NOT NULL,
	"information_gain" real DEFAULT 0 NOT NULL,
	"source_message_ids_json" text DEFAULT '[]' NOT NULL,
	"status" varchar(32) DEFAULT 'active' NOT NULL,
	"version" integer DEFAULT 1 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "corrections" (
	"id" serial PRIMARY KEY NOT NULL,
	"conversation_id" varchar(128) NOT NULL,
	"target" varchar(256) DEFAULT '' NOT NULL,
	"old_value" varchar(1024) DEFAULT '' NOT NULL,
	"new_value" varchar(1024) DEFAULT '' NOT NULL,
	"status" varchar(32) DEFAULT 'active' NOT NULL,
	"source_message_ids_json" text DEFAULT '[]' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "context_versions" (
	"id" serial PRIMARY KEY NOT NULL,
	"conversation_id" varchar(128) NOT NULL,
	"version" integer DEFAULT 1 NOT NULL,
	"state_json" text DEFAULT '{}' NOT NULL,
	"source_message_ids_json" text DEFAULT '[]' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "messages" ADD CONSTRAINT "messages_conversation_id_conversations_id_fk" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "memory_items" ADD CONSTRAINT "memory_items_conversation_id_conversations_id_fk" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "corrections" ADD CONSTRAINT "corrections_conversation_id_conversations_id_fk" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "context_versions" ADD CONSTRAINT "context_versions_conversation_id_conversations_id_fk" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "idx_conversations_user_key" ON "conversations" USING btree ("user_key");--> statement-breakpoint
CREATE INDEX "idx_messages_conversation_id" ON "messages" USING btree ("conversation_id");--> statement-breakpoint
CREATE INDEX "idx_messages_message_key" ON "messages" USING btree ("message_key");--> statement-breakpoint
CREATE UNIQUE INDEX "uq_conv_message_key" ON "messages" USING btree ("conversation_id","message_key");--> statement-breakpoint
CREATE INDEX "idx_memory_items_conversation_id" ON "memory_items" USING btree ("conversation_id");--> statement-breakpoint
CREATE INDEX "idx_memory_items_type" ON "memory_items" USING btree ("type");--> statement-breakpoint
CREATE INDEX "idx_memory_items_topic_key" ON "memory_items" USING btree ("topic_key");--> statement-breakpoint
CREATE INDEX "idx_memory_items_status" ON "memory_items" USING btree ("status");--> statement-breakpoint
CREATE INDEX "idx_corrections_conversation_id" ON "corrections" USING btree ("conversation_id");--> statement-breakpoint
CREATE INDEX "idx_context_versions_conversation_id" ON "context_versions" USING btree ("conversation_id");--> statement-breakpoint
CREATE UNIQUE INDEX "uq_conv_context_version" ON "context_versions" USING btree ("conversation_id","version");