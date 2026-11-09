"""기본 점검 (docs/tool-spec.md의 check)."""

import sqlite3

import pytest

from pipeline.check import check_mission
from pipeline.schema import create_schema

MISSION = "test-mission"


@pytest.fixture
def conn():
    """점검을 모두 통과하는 데이터. 테스트마다 하나씩 망가뜨린다."""
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    conn.execute("INSERT INTO missions VALUES (?, 'owner/repo', '미션', '2026-03-03T09:00:00+09:00')", (MISSION,))
    conn.execute(
        "INSERT INTO pull_requests VALUES (?, 1, 'learner', '미션 제출', '2026-03-01', 'https://github.com/owner/repo/pull/1')",
        (MISSION,),
    )
    for comment_id, author, is_pr_author in ((10, "reviewer", 0), (11, "learner", 1)):
        conn.execute(
            "INSERT INTO comments VALUES (?, ?, 1, 'review', ?, ?, '책임을 나눠 보세요', NULL, NULL, '2026-03-01', '2026-03-01', ?)",
            (comment_id, MISSION, author, is_pr_author, f"https://github.com/owner/repo/pull/1#discussion_r{comment_id}"),
        )
    conn.execute("INSERT INTO topics VALUES ('responsibility', NULL, NULL, '책임 분리')")
    conn.execute("INSERT INTO comment_topics VALUES (10, 'responsibility', 'keyword', 1)")
    return conn


def failed(conn) -> list[str]:
    return [name for name, ok, _ in check_mission(conn, MISSION) if not ok]


def test_망가진_데가_없으면_모두_통과한다(conn):
    assert failed(conn) == []


def test_수집_시각이_없으면_실패한다(conn):
    conn.execute("UPDATE missions SET synced_at = NULL")

    assert failed(conn) == ["수집 시각"]


def test_미션이_없으면_실패한다():
    empty = sqlite3.connect(":memory:")
    create_schema(empty)

    assert "수집 시각" in failed(empty)


def test_PR이_없으면_실패한다(conn):
    conn.execute("DELETE FROM pull_requests")

    assert failed(conn) == ["PR"]


def test_리뷰어_코멘트가_없으면_실패한다(conn):
    conn.execute("DELETE FROM comment_topics")
    conn.execute("DELETE FROM comments WHERE is_pr_author = 0")

    assert failed(conn) == ["리뷰어 코멘트", "주제가 붙은 리뷰어 코멘트"]


def test_원문_링크가_없는_코멘트가_있으면_실패한다(conn):
    conn.execute("UPDATE comments SET url = '' WHERE id = 11")

    assert failed(conn) == ["원문 링크가 없는 코멘트"]


def test_tag를_돌리지_않았으면_실패한다(conn):
    conn.execute("DELETE FROM comment_topics")

    assert failed(conn) == ["주제가 붙은 리뷰어 코멘트"]
