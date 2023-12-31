
data "aws_iam_policy_document" "authorizer" {
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
}

resource "aws_iam_role" "authorizer" {
  name = "${var.prefix}_authorizer"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF

  inline_policy {
    name = "${var.prefix}_authorizer_policy"
    policy = data.aws_iam_policy_document.authorizer.json
  }
}

resource "aws_lambda_function" "authorizer" {
  function_name = "${var.prefix}_authorizer"
  filename      = data.archive_file.lambda_archive.output_path
  role          = aws_iam_role.authorizer.arn
  handler       = "barbot.authorizer.handle_auth"
  architectures = [ "arm64" ]

  timeout = 60

  source_code_hash = data.archive_file.lambda_archive.output_base64sha256

  runtime = local.lambda_runtime

  environment {
    variables = {
      TELEGRAM_BOT_API_SECRET_TOKEN: random_password.webhook_secret.result
    }
  }
}