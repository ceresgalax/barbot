
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
      aws_dynamodb_table.barnight_week.arn
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

#resource "aws_iam_policy" "lambda_policy" {
#  name = "${var.prefix}_application_policy"
#  policy = <<EOF
#{
#    "Version": "2012-10-17",
#    "Statement": [
#        {
#            "Effect": "Allow",
#            "Action": [
#              "logs:CreateLogGroup",
#              "logs:CreateLogStream",
#              "logs:DescribeLogGroups",
#              "logs:DescribeLogStreams",
#              "logs:PutLogEvents",
#              "logs:GetLogEvents",
#              "logs:FilterLogEvents"
#            ],
#            "Resource": "*"
#        },
#        {
#          "Effect": "Allow",
#          "Action": [
#              "dynamodb:BatchGetItem",
#              "dynamodb:GetItem",
#              "dynamodb:Query",
#              "dynamodb:Scan",
#              "dynamodb:BatchWriteItem",
#              "dynamodb:PutItem",
#              "dynamodb:UpdateItem",
#              "dynamodb:DescribeTable"
#          ],
#          "Resource": "*"
#        },
#        {
#          "Effect": "Allow",
#          "Action": [
#            ""scheduler:GetSchedule""
#          ],
#          "Resource": "${}"
#        }
#    ]
#}
#EOF
#}
#
#resource "aws_iam_role_policy_attachment" "app_policy_for_api_lambda" {
#  role = aws_iam_role.api.name
#  policy_arn = aws_iam_policy.lambda_policy.arn
#}


data "archive_file" "lambda_archive" {
  source_dir = "../build/lambda_stage"
  output_path = "../build/lambda.zip"
  type = "zip"
}

locals {
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

  runtime = "python3.9"

  environment {
    variables = {
      MAIN_CHAT_ID: var.main_chat_id
      TELEGRAM_BOT_TOKEN: var.telegram_bot_token,
      TELEGRAM_BOT_API_SECRET_TOKEN: random_password.webhook_secret.result
      BOT_USERNAME: var.bot_username,
      DYNAMO_WEEK_TABLE_NAME: aws_dynamodb_table.barnight_week.name
      SCHEDULE_GROUP_NAME: aws_scheduler_schedule_group.barbot.name
      CREATE_POLL_SCHEDULE_NAME = "${var.prefix}_create_poll"
      CLOSE_POLL_SCHEDULE_NAME = "${var.prefix}_close_poll"
      BAR_SPREADSHEET: var.bar_spreadsheet,
      SELENIUM_SERVER_URL: var.selenium_server_url,
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
  compatible_runtimes = ["python3.9"]
}