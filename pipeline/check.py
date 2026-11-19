"""기본 점검 (docs/tool-spec.md의 check).

배포 전에 자동으로 돌린다. 기준값 없이, 어느 미션에나 늘 맞아야 하는 것만 본다.
직전 DB를 주면 직전보다 덜 들어오지 않았는지도 본다.
"""

import sqlite3

# verify.py와 비슷한 SQL을 일부러 따로 둔다. verify는 분류 품질을 보는 개발 도구라
# 없어질 수 있고, 배포 점검이 그 변화에 함께 깨지지 않게 하기 위해서다.

# PR은 거의 지워지지 않는다. 이만큼 줄면 수집이 끊긴 것으로 본다.
PR_DROP_LIMIT = 5
# 코멘트는 지워질 수 있어서 이만큼 줄어드는 것은 정상으로 본다.
COMMENT_DROP_TOLERANCE = 0.01


def _one(conn: sqlite3.Connection, sql: str, mission_id: str) -> int:
    return conn.execute(sql, (mission_id,)).fetchone()[0]


def _prs(conn: sqlite3.Connection, mission_id: str) -> int:
    return _one(conn, "SELECT COUNT(*) FROM pull_requests WHERE mission_id = ?", mission_id)


def _comments(conn: sqlite3.Connection, mission_id: str) -> int:
    return _one(conn, "SELECT COUNT(*) FROM comments WHERE mission_id = ?", mission_id)


def check_mission(
    conn: sqlite3.Connection, mission_id: str, previous: sqlite3.Connection | None = None
) -> list[tuple[str, bool, object]]:
    """(항목, 통과 여부, 실제 값) 목록을 돌려준다. previous는 직전 DB."""
    synced_at = conn.execute("SELECT synced_at FROM missions WHERE id = ?", (mission_id,)).fetchone()
    synced_at = synced_at[0] if synced_at else None
    prs = _prs(conn, mission_id)
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

    results = [
        ("수집 시각", synced_at is not None, synced_at),
        ("PR", prs > 0, prs),
        ("리뷰어 코멘트", reviewer_comments > 0, reviewer_comments),
        ("원문 링크가 없는 코멘트", no_link == 0, no_link),
        ("주제가 붙은 리뷰어 코멘트", tagged > 0, tagged),
    ]
    if previous is None:
        return results

    # 직전 DB에 없던 미션은 직전 값이 0이라 늘 통과한다.
    previous_prs = _prs(previous, mission_id)
    comments, previous_comments = _comments(conn, mission_id), _comments(previous, mission_id)
    return results + [
        ("직전 대비 PR", previous_prs - prs < PR_DROP_LIMIT, f"{previous_prs} → {prs}"),
        (
            "직전 대비 코멘트",
            previous_comments - comments <= previous_comments * COMMENT_DROP_TOLERANCE,
            f"{previous_comments} → {comments}",
        ),
    ]


def print_check(conn: sqlite3.Connection, mission_id: str, previous: sqlite3.Connection | None = None) -> bool:
    """점검 결과를 표로 출력한다. 모두 통과하면 True."""
    results = check_mission(conn, mission_id, previous)
    for name, ok, value in results:
        print(f"{'OK  ' if ok else '실패'}  {name:<16}  {value}")
    return all(ok for _, ok, _ in results)
