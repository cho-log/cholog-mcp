variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "name" {
  description = "모든 자원 이름의 앞부분. 같은 계정의 다른 프로젝트와 겹치지 않게 한다"
  type        = string
  default     = "cholog-mcp"
}

variable "image_tag" {
  description = "배포할 이미지 태그. git 커밋 해시를 쓴다 (예: ab269df)"
  type        = string
}

variable "allowed_hosts" {
  description = "서버가 받을 Host 헤더 값. Function URL 도메인은 만든 뒤에야 알 수 있어서, 처음엔 비우고 두 번째 apply에서 넣는다"
  type        = list(string)
  default     = []
}

variable "invocation_alarm_threshold" {
  description = "5분간 호출 수가 이 값을 넘으면 차단 스위치가 함수를 막는다. 리드 몇 명의 정상 사용으로는 닿지 않는 값"
  type        = number
  default     = 300
}

variable "alert_email" {
  description = "차단 알림을 받을 메일. 공개 저장소라 terraform.tfvars(git 제외)에 둔다"
  type        = string
}
