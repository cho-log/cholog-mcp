output "ecr_repository_url" {
  description = "docker push 할 주소"
  value       = aws_ecr_repository.server.repository_url
}

output "function_url" {
  description = "AI 앱에 등록할 주소는 이 뒤에 mcp를 붙인 것"
  value       = aws_lambda_function_url.server.function_url
}

output "function_url_host" {
  description = "allowed_hosts에 넣을 값"
  value       = trimsuffix(trimprefix(aws_lambda_function_url.server.function_url, "https://"), "/")
}
