variable "prefix" {
  description = "Prefix for all AWS resource names"
  type        = string
}

variable "aws_region" {
  default     = "us-west-2"
  description = "AWS Region to deploy resources to."
  type        = string
}

variable "main_chat_id" {
  description = "Telegram chat ID that the bot considers home."
  type        = string
}

variable "bot_username" {
  description = "Telegram username of the bot. Don't include the @."
  type        = string
}

variable "telegram_bot_token" {
  description = "Bot token for this bot from the Telegram botfather."
  type        = string
  sensitive   = true
}

variable "bar_spreadsheet" {
  description = "URL of the Google Docs sheet containing the known bars."
  type        = string
  sensitive   = true
}

variable "selenium_server_url" {
  description = "URL of a Selenium server (Grid) used for rendering images."
  type        = string
  sensitive   = true
}

variable "timezone" {
  description = "Timezone to use for scheduled event times"
  type        = string
}

variable "first_reminder_cron" {
  description = "Cron expression for when a reminder should be sent before creating the poll. (Amazon EventBridge Scheduler syntax)"
  type        = string
}

variable "create_poll_cron" {
  description = "Cron expression for when the poll should be created. (Amazon EventBridge Scheduler syntax)"
  type        = string
}

variable "last_call_cron" {
  description = "Cron expression for when the last call message should be sent. (Amazon EventBridge Scheduler syntax)"
  type        = string
}

variable "close_poll_cron" {
  description = "Cron expression for when the poll should be closed. (Amazon EventBridge Scheduler syntax)"
  type        = string
}
