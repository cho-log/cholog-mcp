# 이미지 보관소. 태그를 덮어쓸 수 없게 해서, 태그(커밋 해시)만 보고 배포된 코드를 알 수 있게 한다.
resource "aws_ecr_repository" "server" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true # destroy할 때 이미지가 남아 있어도 지운다 (팀 계정으로 옮길 때)
}

resource "aws_ecr_lifecycle_policy" "server" {
  repository = aws_ecr_repository.server.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "최근 이미지 5개만 남긴다"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

# Lambda가 쓰는 신원. 로그를 쓰는 권한만 준다.
resource "aws_iam_role" "server" {
  name = var.name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# 함수보다 먼저 만든다. Lambda가 자동으로 만들면 보관 기간이 "영구"가 된다.
resource "aws_cloudwatch_log_group" "server" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "server" {
  function_name = var.name
  role          = aws_iam_role.server.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.server.repository_url}:${var.image_tag}"
  architectures = ["arm64"]
  memory_size   = 512 # CPU도 메모리에 비례해 붙는다. 깨어나는 시간을 줄이려고 기본(128)보다 크게 둔다
  timeout       = 30  # 도구 호출은 0.1초 안팎. 열린 요청이 오래 붙잡지 못하게 짧게 둔다

  dynamic "environment" {
    for_each = length(var.allowed_hosts) > 0 ? [1] : []
    content {
      variables = {
        CHOLOG_ALLOWED_HOSTS = join(",", var.allowed_hosts)
      }
    }
  }

  # 동시 실행 수는 차단 스위치(kill_switch.tf)가 0으로 바꾼다. apply가 차단을 몰래 풀지 않도록 Terraform은 이 값을 관리하지 않는다.
  lifecycle {
    ignore_changes = [reserved_concurrent_executions]
  }

  depends_on = [aws_cloudwatch_log_group.server, aws_iam_role_policy_attachment.logs]
}

# 함수에 붙는 공개 HTTPS 주소. 시연용이라 인증은 없다.
# 인증 없는 URL에 필요한 권한 두 개(lambda:InvokeFunctionUrl, URL로 온 lambda:InvokeFunction)는
# provider가 URL을 만들 때 자동으로 넣는다. 따로 선언하면 같은 ID로 충돌한다. destroy해도 지워지지 않는다.
resource "aws_lambda_function_url" "server" {
  function_name      = aws_lambda_function.server.function_name
  authorization_type = "NONE"
  invoke_mode        = "BUFFERED"
}
