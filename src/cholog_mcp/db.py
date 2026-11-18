"""SQLite 연결."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from cholog_mcp.config import db_path

SCHEMA_ERROR = "지원하지 않는 DB 스키마다. 최신 스키마로 새 DB를 생성하고 원본을 적재·분류한다."


@contextmanager
def open_db() -> Iterator[sqlite3.Connection]:
    """읽기 전용으로 연다. 서버는 데이터를 바꾸지 않는다."""
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"데이터 파일이 없다: {path.resolve()}. `uv run python -m pipeline load <mission>`으로 먼저 만든다."
        )
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        yield conn
    finally:
        conn.close()


def has_comment_identity_constraints(conn: sqlite3.Connection) -> bool:
    """댓글 ID 충돌을 막는 제약을 읽기만 한다. 열 이름만으로 스키마 호환성을 판단하지 않는다."""
    columns = {row[1]: row for row in conn.execute("PRAGMA table_info(comments)")}
    if not {"id", "github_id", "mission_id", "kind", "in_reply_to_id"} <= columns.keys():
        return False
    if [row[1] for row in columns.values() if row[5]] != ["id"] or columns["id"][2].upper() != "INTEGER":
        return False
    if columns["github_id"][2].upper() != "INTEGER" or not columns["github_id"][3]:
        return False
    if columns["in_reply_to_id"][2].upper() != "INTEGER" or columns["in_reply_to_id"][3]:
        return False
    if not all(columns[name][3] for name in ("mission_id", "kind")):
        return False
    indexes = conn.execute("PRAGMA index_list(comments)").fetchall()
    # rowid 별칭은 별도 PK 인덱스가 없다. WITHOUT ROWID나 컬럼 수준 PK DESC는 자동 ID가 아니다.
    if any(index[3] == "pk" for index in indexes):
        return False
    for index in indexes:
        if not index[2] or index[4]:  # 유일 인덱스이며 모든 행에 적용되어야 한다.
            continue
        names = tuple(row[0] for row in conn.execute(
            "SELECT name FROM pragma_index_info(?) ORDER BY seqno", (index[1],),
        ))
        if names == ("mission_id", "kind", "github_id"):
            return True
    return False
