
data "aws_iam_policy_document" "lambda_assume_role_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect = "Allow"
    principals {
      identifiers = ["lambda.amazonaws.com"]
      type        = "Service"
    }
    principals {
      identifiers = ["scheduler.amazonaws.com"]
      type        = "Service"
    }
  }
}

data "aws_iam_policy_document" "lambda" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
      "logs:GetLogEvents",
      "logs:FilterLogEvents"
    ]
    resources = ["*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:BatchGetItem",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchWriteItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable"
    ]
    resources = [
      aws_dynamodb_table.barnight_week.arn,
      aws_dynamodb_table.barnight_events.arn
    ]
  }
  statement {
    effect = "Allow"
    actions = [
      "scheduler:GetSchedule"
    ]
    resources = [
      "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule/${aws_scheduler_schedule_group.barbot.name}/*"
    ]
  }
}

resource "aws_iam_role" "api" {
  name = "${var.prefix}_lambda_role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role_policy.json
  inline_policy {
    name = "${var.prefix}_application_policy"
    policy = data.aws_iam_policy_document.lambda.json
  }
}

data "archive_file" "lambda_archive" {
  source_dir = "../build/lambda_stage"
  output_path = "../build/lambda.zip"
  type = "zip"
}

locals {
  lambda_runtime = "python3.12"

  functions = {
    webhook = {
      handler = "barbot.webhook.handle_webhook"
    }
    sequence = {
      handler = "barbot.sequence.handle_function_call"
    }
  }
}

resource "aws_lambda_function" "api" {
  for_each = local.functions

  function_name = "${var.prefix}-${each.key}"
  filename      = data.archive_file.lambda_archive.output_path
  role          = aws_iam_role.api.arn
  handler       = each.value.handler
  architectures = [ "arm64" ]

  timeout = 60

  source_code_hash = data.archive_file.lambda_archive.output_base64sha256

  runtime = local.lambda_runtime

  environment {
    variables = {
      MAIN_CHAT_ID: var.main_chat_id
      TELEGRAM_BOT_TOKEN: var.telegram_bot_token,
      TELEGRAM_BOT_API_SECRET_TOKEN: random_password.webhook_secret.result
      BOT_USERNAME: var.bot_username,
      DYNAMO_WEEK_TABLE_NAME: aws_dynamodb_table.barnight_week.name
      DYNAMO_EVENTS_TABLE_NAME: aws_dynamodb_table.barnight_events.name
      SCHEDULE_GROUP_NAME: aws_scheduler_schedule_group.barbot.name
      CREATE_POLL_SCHEDULE_NAME = "${var.prefix}_create_poll"
      CLOSE_POLL_SCHEDULE_NAME = "${var.prefix}_close_poll"
      BAR_SPREADSHEET: var.bar_spreadsheet,
      SELENIUM_SERVER_URL: var.selenium_server_url,
      ANNOUNCEMENT_CHAT_ID: var.announcement_chat_id,
      MAIN_EVENT_TIMEZONE: var.timezone,
      MAIN_EVENT_CRON: var.main_event_cron,
      MAIN_EVENT_DURATION_MINUTES: tostring(var.main_event_duration_minutes)
    }
  }

  layers = [
      aws_lambda_layer_version.libs.arn
  ]
}

data "archive_file" "libs" {
  source_dir = "../build/libs"
  output_path = "../build/libs.zip"
  type = "zip"
}

resource "aws_lambda_layer_version" "libs" {
  layer_name = "${var.prefix}-libs"
  filename = data.archive_file.libs.output_path
  source_code_hash = data.archive_file.libs.output_base64sha256
  compatible_runtimes = [local.lambda_runtime]
}