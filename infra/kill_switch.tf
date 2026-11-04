# 차단 스위치: 호출 수가 기준을 넘으면 서버 함수를 막고 메일을 보낸다.
# 예산 알림은 몇 시간 늦게 알려 줄 뿐이라, 공격은 여기서 몇 분 안에 막는다.
#
#   호출 급증 → 알람 → SNS ─┬→ 메일
#                           └→ 차단용 Lambda → 서버 함수 동시 실행 = 0 (이후 요청은 429)

resource "aws_sns_topic" "alerts" {
  name = "${var.name}-alerts"
}

# 처음에 "구독 확인" 메일이 온다. 링크를 눌러야 받기 시작한다.
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "invocations" {
  alarm_name          = "${var.name}-invocations-spike"
  alarm_description   = "5분간 호출 수가 ${var.invocation_alarm_threshold}회를 넘었다. 차단 스위치가 함수를 막는다"
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  dimensions          = { FunctionName = aws_lambda_function.server.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.invocation_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

data "archive_file" "kill_switch" {
  type        = "zip"
  source_file = "${path.module}/kill_switch/handler.py"
  output_path = "${path.module}/.build/kill_switch.zip"
}

resource "aws_iam_role" "kill_switch" {
  name = "${var.name}-kill-switch"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "kill_switch_logs" {
  role       = aws_iam_role.kill_switch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# 서버 함수 하나의 동시 실행 수만 바꿀 수 있다.
resource "aws_iam_role_policy" "kill_switch" {
  role = aws_iam_role.kill_switch.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:PutFunctionConcurrency"
      Resource = aws_lambda_function.server.arn
    }]
  })
}

resource "aws_cloudwatch_log_group" "kill_switch" {
  name              = "/aws/lambda/${var.name}-kill-switch"
  retention_in_days = 14
}

resource "aws_lambda_function" "kill_switch" {
  function_name    = "${var.name}-kill-switch"
  role             = aws_iam_role.kill_switch.arn
  runtime          = "python3.13"
  handler          = "handler.handler"
  architectures    = ["arm64"]
  filename         = data.archive_file.kill_switch.output_path
  source_code_hash = data.archive_file.kill_switch.output_base64sha256
  timeout          = 10

  environment {
    variables = { TARGET_FUNCTION = aws_lambda_function.server.function_name }
  }

  depends_on = [aws_cloudwatch_log_group.kill_switch, aws_iam_role_policy_attachment.kill_switch_logs]
}

resource "aws_lambda_permission" "kill_switch_sns" {
  statement_id  = "AllowSNSInvoke"
  function_name = aws_lambda_function.kill_switch.function_name
  action        = "lambda:InvokeFunction"
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.alerts.arn
}

resource "aws_sns_topic_subscription" "kill_switch" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.kill_switch.arn
}
