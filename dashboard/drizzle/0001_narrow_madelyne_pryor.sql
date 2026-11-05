CREATE TABLE `friendships` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`requester_id` text NOT NULL,
	`addressee_id` text NOT NULL,
	`status` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`requester_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`addressee_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `friendships_pair` ON `friendships` (`requester_id`,`addressee_id`);--> statement-breakpoint
CREATE INDEX `friendships_addressee` ON `friendships` (`addressee_id`);--> statement-breakpoint
CREATE TABLE `print_permissions` (
	`grantor_id` text NOT NULL,
	`grantee_id` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`grantor_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`grantee_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `print_permissions_pair` ON `print_permissions` (`grantor_id`,`grantee_id`);--> statement-breakpoint
CREATE TABLE `print_requests` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`sender_id` text NOT NULL,
	`recipient_id` text NOT NULL,
	`title` text NOT NULL,
	`detail` text DEFAULT '' NOT NULL,
	`bitmap` text,
	`created_at` integer NOT NULL,
	`claimed_device_id` text,
	`delivered_at` integer,
	FOREIGN KEY (`sender_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`recipient_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `print_requests_recipient` ON `print_requests` (`recipient_id`,`delivered_at`);--> statement-breakpoint
CREATE INDEX `print_requests_sender` ON `print_requests` (`sender_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `profiles` (
	`user_id` text PRIMARY KEY NOT NULL,
	`friend_code` text NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `profiles_friend_code_unique` ON `profiles` (`friend_code`);--> statement-breakpoint
ALTER TABLE `items` ADD `bitmap` text;