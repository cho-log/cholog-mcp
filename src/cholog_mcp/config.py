"""실행 환경에서 받는 설정."""

import os
from pathlib import Path

DB_PATH_ENV = "CHOLOG_DB_PATH"
DEFAULT_DB_PATH = "data/cholog.db"


def db_path() -> Path:
    """SQLite 파일 경로. 환경 변수 CHOLOG_DB_PATH가 없으면 기본값을 쓴다."""
    return Path(os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH))
