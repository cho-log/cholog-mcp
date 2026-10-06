import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.load import load_mission, read_json_arrays
from pipeline.missions import Mission
from pipeline.schema import create_schema

MISSION = Mission(id="test-mission", repo="owner/repo", name="테스트 미션")


def _comment(comment_id: int, login: str, body: str, **extra) -> dict:
    return {
        "id": comment_id,
        "user": {"login": login},
        "body": body,
        "created_at": "2026-03-01T00:00:00Z",
        "updated_at": "2026-03-02T00:00:00Z",
        "html_url": f"https://github.com/owner/repo/pull/1#discussion_r{comment_id}",
        **extra,
    }


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    (tmp_path / "review").mkdir()
    (tmp_path / "issue").mkdir()
    prs = [
        {"number": 1, "author": {"login": "learner"}, "title": "[스터디] 미션 제출", "createdAt": "2026-03-01T00:00:00Z"},
        {"number": 2, "author": {"login": "other"}, "title": "리뷰 없는 PR", "createdAt": "2026-03-01T00:00:00Z"},
    ]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    # gh api --paginate처럼 배열 두 개를 이어 붙인다.
    review_pages = [
        [_comment(10, "reviewer", "책임을 나눠 보세요", path="Car.java", diff_hunk="@@ -1 +1 @@")],
        [_comment(11, "learner", "고쳤습니다", path="Car.java", diff_hunk="@@ -1 +1 @@")],
    ]
    (tmp_path / "review" / "1.json").write_text("".join(json.dumps(page) for page in review_pages), encoding="utf-8")
    (tmp_path / "issue" / "1.json").write_text(json.dumps([_comment(20, "reviewer", "수고하셨습니다")]), encoding="utf-8")
    (tmp_path / "meta.json").write_text(json.dumps({"fetched_at": "2026-03-03T09:00:00+09:00"}), encoding="utf-8")
    return tmp_path


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    return conn


def test_PR과_코멘트를_넣는다(conn, raw_dir):
    loaded = load_mission(conn, MISSION, raw_dir)

    assert loaded == {"pull_requests": 2, "comments": 3}
    assert conn.execute("SELECT number, author, url FROM pull_requests ORDER BY number").fetchall() == [
        (1, "learner", "https://github.com/owner/repo/pull/1"),
        (2, "other", "https://github.com/owner/repo/pull/2"),
    ]


def test_PR_작성자_본인의_코멘트를_표시한다(conn, raw_dir):
    load_mission(conn, MISSION, raw_dir)

    rows = conn.execute("SELECT id, kind, author, is_pr_author FROM comments ORDER BY id").fetchall()
    assert rows == [(10, "review", "reviewer", 0), (11, "review", "learner", 1), (20, "issue", "reviewer", 0)]


def test_원문_링크와_수집_시각을_남긴다(conn, raw_dir):
    load_mission(conn, MISSION, raw_dir)

    assert conn.execute("SELECT url FROM comments WHERE id = 10").fetchone()[0].endswith("#discussion_r10")
    assert conn.execute("SELECT synced_at FROM missions").fetchone()[0] == "2026-03-03T09:00:00+09:00"


def test_다시_넣으면_통째로_바뀐다(conn, raw_dir):
    load_mission(conn, MISSION, raw_dir)
    load_mission(conn, MISSION, raw_dir)

    assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 3


def test_이어_붙은_배열과_없는_파일을_읽는다(raw_dir):
    assert [c["id"] for c in read_json_arrays(raw_dir / "review" / "1.json")] == [10, 11]
    assert read_json_arrays(raw_dir / "review" / "2.json") == []
