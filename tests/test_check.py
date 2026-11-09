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


def copy_of(conn) -> sqlite3.Connection:
    """직전 DB로 쓸 복사본. 열린 트랜잭션이 있으면 복사가 잠금에서 기다리므로 먼저 커밋한다."""
    conn.commit()
    previous = sqlite3.connect(":memory:")
    conn.backup(previous)
    return previous


def add_comments(conn, count: int) -> None:
    for comment_id in range(100, 100 + count):
        conn.execute(
            "INSERT INTO comments VALUES (?, ?, 1, 'issue', 'reviewer', 0, '좋아요', NULL, NULL, '2026-03-01', '2026-03-01', ?)",
            (comment_id, MISSION, f"https://github.com/owner/repo/pull/1#issuecomment-{comment_id}"),
        )


def failed_against(conn, previous) -> list[str]:
    return [name for name, ok, _ in check_mission(conn, MISSION, previous) if not ok]


def test_직전과_같으면_통과한다(conn):
    assert failed_against(conn, copy_of(conn)) == []


def test_직전보다_늘면_통과한다(conn):
    previous = copy_of(conn)
    conn.execute(
        "INSERT INTO pull_requests VALUES (?, 2, 'other', '미션 제출', '2026-03-02', 'https://github.com/owner/repo/pull/2')",
        (MISSION,),
    )
    add_comments(conn, 3)

    assert failed_against(conn, previous) == []


def add_prs(conn, count: int) -> None:
    for number in range(2, 2 + count):
        conn.execute(
            "INSERT INTO pull_requests VALUES (?, ?, 'other', '미션 제출', '2026-03-02', ?)",
            (MISSION, number, f"https://github.com/owner/repo/pull/{number}"),
        )


def test_PR이_4개까지_줄면_통과한다(conn):
    add_prs(conn, 9)  # 모두 10개
    previous = copy_of(conn)
    conn.execute("DELETE FROM pull_requests WHERE number BETWEEN 2 AND 5")  # 10 → 6

    assert failed_against(conn, previous) == []


def test_PR이_5개_이상_줄면_실패한다(conn):
    add_prs(conn, 9)
    previous = copy_of(conn)
    conn.execute("DELETE FROM pull_requests WHERE number BETWEEN 2 AND 6")  # 10 → 5

    assert failed_against(conn, previous) == ["직전 대비 PR"]


def test_코멘트가_1퍼센트_이하로_줄면_통과한다(conn):
    add_comments(conn, 198)  # 모두 200개
    previous = copy_of(conn)
    conn.execute("DELETE FROM comments WHERE id IN (100, 101)")  # 200 → 198, 1%

    assert failed_against(conn, previous) == []


def test_코멘트가_1퍼센트_넘게_줄면_실패한다(conn):
    add_comments(conn, 198)
    previous = copy_of(conn)
    conn.execute("DELETE FROM comments WHERE id IN (100, 101, 102)")  # 200 → 197, 1.5%

    assert failed_against(conn, previous) == ["직전 대비 코멘트"]


def test_직전_DB에_없던_미션은_통과한다(conn):
    previous = sqlite3.connect(":memory:")
    create_schema(previous)

    assert failed_against(conn, previous) == []


def test_check는_DB_파일이_없으면_만들지_않고_실패한다(tmp_path, monkeypatch):
    missing = tmp_path / "missing.db"
    monkeypatch.setenv("CHOLOG_DB_PATH", str(missing))
    monkeypatch.setattr("sys.argv", ["pipeline", "check", "java-racingcar"])

    from pipeline.__main__ import main

    assert main() == 1
    assert not missing.exists()


def test_직전_DB가_SQLite가_아니면_이유를_알리고_실패한다(conn, tmp_path, monkeypatch, capsys):
    db = tmp_path / "cholog.db"
    conn.commit()
    conn.backup(sqlite3.connect(db))
    not_sqlite = tmp_path / "previous #1.db"  # 경로에 #가 있어도 열려야 한다
    not_sqlite.write_text("not a database")
    monkeypatch.setenv("CHOLOG_DB_PATH", str(db))
    monkeypatch.setattr("sys.argv", ["pipeline", "check", "java-racingcar", "--previous", str(not_sqlite)])

    from pipeline.__main__ import main

    assert main() == 1
    assert "직전 DB를 읽을 수 없다" in capsys.readouterr().out
