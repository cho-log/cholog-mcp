"""기본 점검 (docs/tool-spec.md의 check).

배포 전에 자동으로 돌린다. 기준값 없이, 어느 미션에나 늘 맞아야 하는 것만 본다.
"""

import sqlite3


def _one(conn: sqlite3.Connection, sql: str, mission_id: str) -> int:
    return conn.execute(sql, (mission_id,)).fetchone()[0]


def check_mission(conn: sqlite3.Connection, mission_id: str) -> list[tuple[str, bool, object]]:
    """(항목, 통과 여부, 실제 값) 목록을 돌려준다."""
    synced_at = conn.execute("SELECT synced_at FROM missions WHERE id = ?", (mission_id,)).fetchone()
    synced_at = synced_at[0] if synced_at else None
    prs = _one(conn, "SELECT COUNT(*) FROM pull_requests WHERE mission_id = ?", mission_id)
    reviewer_comments = _one(
        conn, "SELECT COUNT(*) FROM comments WHERE mission_id = ? AND is_pr_author = 0", mission_id)
    no_link = _one(
        conn, "SELECT COUNT(*) FROM comments WHERE mission_id = ? AND url NOT LIKE 'https://github.com/%'",
        mission_id)
    tagged = _one(
        conn,
        "SELECT COUNT(DISTINCT c.id) FROM comments c JOIN comment_topics ct ON ct.comment_id = c.id "
        "WHERE c.mission_id = ? AND c.is_pr_author = 0",
        mission_id)

    return [
        ("수집 시각", synced_at is not None, synced_at),
        ("PR", prs > 0, prs),
        ("리뷰어 코멘트", reviewer_comments > 0, reviewer_comments),
        ("원문 링크가 없는 코멘트", no_link == 0, no_link),
        ("주제가 붙은 리뷰어 코멘트", tagged > 0, tagged),
    ]


def print_check(conn: sqlite3.Connection, mission_id: str) -> bool:
    """점검 결과를 표로 출력한다. 모두 통과하면 True."""
    results = check_mission(conn, mission_id)
    for name, ok, value in results:
        print(f"{'OK  ' if ok else '실패'}  {name:<16}  {value}")
    return all(ok for _, ok, _ in results)
