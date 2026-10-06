"""SQLite 연결."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from cholog_mcp.config import db_path


@contextmanager
def open_db() -> Iterator[sqlite3.Connection]:
    """읽기 전용으로 연다. 서버는 데이터를 바꾸지 않는다."""
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"데이터 파일이 없다: {path.resolve()}. `uv run python -m pipeline load <mission>`으로 먼저 만든다."
        )
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        yield conn
    finally:
        conn.close()
