CREATE TABLE `conversations` (
	`id` text(128) PRIMARY KEY NOT NULL,
	`user_key` text(128),
	`created_at` text DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	`updated_at` text DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	`metadata_json` text
);
--> statement-breakpoint
CREATE INDEX `idx_conversations_user_key` ON `conversations` (`user_key`);--> statement-breakpoint
CREATE TABLE `messages` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`conversation_id` text(128) NOT NULL,
	`message_key` text(128) NOT NULL,
	`role` text(32) NOT NULL,
	`content` text NOT NULL,
	`content_hash` text(64) NOT NULL,
	`ordinal` integer DEFAULT 0 NOT NULL,
	`client_message_id` text(128),
	`metadata_json` text,
	`created_at` text DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_messages_conversation_id` ON `messages` (`conversation_id`);--> statement-breakpoint
CREATE INDEX `idx_messages_message_key` ON `messages` (`message_key`);--> statement-breakpoint
CREATE UNIQUE INDEX `uq_conv_message_key` ON `messages` (`conversation_id`,`message_key`);--> statement-breakpoint
CREATE TABLE `memory_items` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`conversation_id` text(128) NOT NULL,
	`content` text NOT NULL,
	`type` text(64) NOT NULL,
	`topic_key` text(128) DEFAULT '' NOT NULL,
	`confidence` real DEFAULT 0 NOT NULL,
	`importance` real DEFAULT 0 NOT NULL,
	`stability` real DEFAULT 0 NOT NULL,
	`freshness` real DEFAULT 0 NOT NULL,
	`information_gain` real DEFAULT 0 NOT NULL,
	`source_message_ids_json` text DEFAULT '[]' NOT NULL,
	`status` text(32) DEFAULT 'active' NOT NULL,
	`version` integer DEFAULT 1 NOT NULL,
	`created_at` text DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	`updated_at` text DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_memory_items_conversation_id` ON `memory_items` (`conversation_id`);--> statement-breakpoint
CREATE INDEX `idx_memory_items_type` ON `memory_items` (`type`);--> statement-breakpoint
CREATE INDEX `idx_memory_items_topic_key` ON `memory_items` (`topic_key`);--> statement-breakpoint
CREATE INDEX `idx_memory_items_status` ON `memory_items` (`status`);--> statement-breakpoint
CREATE TABLE `corrections` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`conversation_id` text(128) NOT NULL,
	`target` text(256) DEFAULT '' NOT NULL,
	`old_value` text(1024) DEFAULT '' NOT NULL,
	`new_value` text(1024) DEFAULT '' NOT NULL,
	`status` text(32) DEFAULT 'active' NOT NULL,
	`source_message_ids_json` text DEFAULT '[]' NOT NULL,
	`created_at` text DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_corrections_conversation_id` ON `corrections` (`conversation_id`);--> statement-breakpoint
CREATE TABLE `context_versions` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`conversation_id` text(128) NOT NULL,
	`version` integer DEFAULT 1 NOT NULL,
	`state_json` text DEFAULT '{}' NOT NULL,
	`source_message_ids_json` text DEFAULT '[]' NOT NULL,
	`created_at` text DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_context_versions_conversation_id` ON `context_versions` (`conversation_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `uq_conv_context_version` ON `context_versions` (`conversation_id`,`version`);