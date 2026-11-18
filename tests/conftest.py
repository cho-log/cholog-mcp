"""공개 가능한 고정 합성 데이터. 네트워크와 실제 스터디 자료를 쓰지 않는다."""

import json
import sqlite3

import pytest

from cholog_mcp.missions import MISSIONS
from pipeline.load import load_mission
from pipeline.schema import create_schema

MISSION = "java-racingcar"
AS_OF = "2026-03-03T09:00:00+09:00"
BODY = "> 이전 설명을 인용합니다.\r\n\r\n선택 이유를 이야기해 볼까요?  \n" + "문맥 " * 120


def raw_comment(id, author="reviewer-id", body="설명을 확인했습니다.", **extra):
    return {
        "id": id, "user": {"login": author}, "body": body,
        "html_url": f"https://github.com/owner/repo/pull/1#discussion_r{id}",
        "path": "src/Car.java", "diff_hunk": "@@ -1 +1 @@\n+ example();",
        "created_at": f"2026-03-01T01:00:{id % 60:02d}Z",
        "updated_at": "2026-03-02T00:00:00Z", **extra,
    }


@pytest.fixture
def review_raw(tmp_path):
    raw = tmp_path / "raw"
    (raw / "review").mkdir(parents=True)
    (raw / "issue").mkdir()
    prs = [
        {"number": n, "author": {"login": author}, "title": f"제출 {n}", "createdAt": created}
        for n, author, created in [
            (1, "Learner-01", "2026-03-01T00:00:00Z"),
            (2, "learner-02", "2026-02-28T23:59:59Z"),
            (3, "learner-01", "2026-03-02T00:00:00Z"),
            (4, "outsider-id", "2026-03-01T00:00:00Z"),
        ]
    ]
    (raw / "prs.json").write_text(json.dumps(prs))
    (raw / "meta.json").write_text(json.dumps({"fetched_at": AS_OF}))
    (raw / "review/1.json").write_text(json.dumps([
        raw_comment(10, body=BODY),
        raw_comment(11, "learner-01", "왜 이 선택이 나을까요?", in_reply_to_id=10),
        raw_comment(12, body="조건이 달라지면 다른 선택도 가능합니다. 합의했습니다.", in_reply_to_id=11),
        raw_comment(13, in_reply_to_id=999),
        raw_comment(14, "learner-01", in_reply_to_id=13),
        raw_comment(15, in_reply_to_id=20),
    ]))
    (raw / "issue/1.json").write_text(json.dumps([
        raw_comment(10, "learner-01", "일반 PR 질문", path=None, diff_hunk=None,
                    html_url="https://github.com/owner/repo/pull/1#issuecomment-10"),
        raw_comment(20, body="일반 PR 답변", path=None, diff_hunk=None,
                    html_url="https://github.com/owner/repo/pull/1#issuecomment-20"),
    ]))
    (raw / "review/2.json").write_text(json.dumps([raw_comment(999)]))
    (raw / "review/4.json").write_text(json.dumps([raw_comment(400)]))
    return raw


@pytest.fixture
def context_db_file(tmp_path, review_raw, monkeypatch):
    path = tmp_path / "context.db"
    with sqlite3.connect(path) as conn:
        create_schema(conn)
        load_mission(conn, MISSIONS[MISSION], review_raw)
    monkeypatch.setenv("CHOLOG_DB_PATH", str(path))
    return path


@pytest.fixture
def review_conn(context_db_file):
    conn = sqlite3.connect(context_db_file)
    try:
        yield conn
    finally:
        conn.close()
