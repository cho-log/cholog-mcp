"""실행 환경에서 받는 설정."""

import os
from pathlib import Path

DB_PATH_ENV = "CHOLOG_DB_PATH"
DEFAULT_DB_PATH = "data/cholog.db"


def db_path() -> Path:
    """SQLite 파일 경로. 환경 변수 CHOLOG_DB_PATH가 없으면 기본값을 쓴다."""
    return Path(os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH))


HTTP_HOST_ENV = "CHOLOG_HTTP_HOST"
HTTP_PORT_ENV = "CHOLOG_HTTP_PORT"
ALLOWED_HOSTS_ENV = "CHOLOG_ALLOWED_HOSTS"
LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]


def http_host() -> str:
    """HTTP 서버가 요청을 받을 주소. 기본은 내 컴퓨터에서만 받는다. 배포할 땐 0.0.0.0."""
    return os.environ.get(HTTP_HOST_ENV, "127.0.0.1")


def http_port() -> int:
    return int(os.environ.get(HTTP_PORT_ENV, "8080"))


def allowed_hosts() -> list[str]:
    """요청의 Host 헤더로 받을 값. 쉼표로 구분한다. 없으면 로컬 주소만 받는다.

    배포할 땐 서버의 도메인(예: Lambda Function URL의 호스트)을 넣는다.
    """
    value = os.environ.get(ALLOWED_HOSTS_ENV)
    if not value:
        return LOCAL_HOSTS
    return [host.strip() for host in value.split(",") if host.strip()]
