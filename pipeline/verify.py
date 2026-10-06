"""적재와 분류 결과를 기준값과 비교한다 (docs/tool-spec.md의 검증 기준 7-1, 7-2).

기준값은 미션을 손으로 분석해 얻은 숫자다. 데이터를 새로 수집하면 달라지므로,
그때는 달라진 이유를 확인하고 기준값을 고친다.
"""

import sqlite3

# 2026-09-15 수집분 기준.
EXPECTED = {
    "java-racingcar": {
        "counts": {
            "PR": 215,
            "코멘트": 4855,
            "리뷰어 코멘트": 2940,
            "PR 작성자 본인 코멘트": 1915,
            "리뷰어 코멘트가 달린 PR": 173,
            "리뷰어": 74,
            "원문 링크가 없는 코멘트": 0,
        },
        # 개념별로 지적받은 PR의 비율(%). 분모는 리뷰어 코멘트가 달린 PR.
        "concept_percent": {
            "naming": 71,
            "exception": 69,
            "responsibility": 69,
            "readability": 66,
            "data-structure": 52,
            "test-writing": 45,
            "layering": 42,
            "abstraction": 40,
            "magic-number": 37,
            "value-object": 27,
        },
        # 세부 지적이 붙으면 개념도 붙이므로 이 값보다 늘 수 있다.
        "concept_percent_at_least": {"testability-random": 61},
        "subtopic_prs": {
            "random-test-only-code": 22,
            "random-new-each-time": 16,
            "random-in-name": 11,
            "random-test-itself": 9,
            "random-luck-test": 9,
            "random-inherit": 8,
        },
    }
}


def _one(conn: sqlite3.Connection, sql: str, mission_id: str) -> int:
    return conn.execute(sql, (mission_id,)).fetchone()[0]


def measure_counts(conn: sqlite3.Connection, mission_id: str) -> dict[str, int]:
    return {
        "PR": _one(conn, "SELECT COUNT(*) FROM pull_requests WHERE mission_id = ?", mission_id),
        "코멘트": _one(conn, "SELECT COUNT(*) FROM comments WHERE mission_id = ?", mission_id),
        "리뷰어 코멘트": _one(
            conn, "SELECT COUNT(*) FROM comments WHERE mission_id = ? AND is_pr_author = 0", mission_id),
        "PR 작성자 본인 코멘트": _one(
            conn, "SELECT COUNT(*) FROM comments WHERE mission_id = ? AND is_pr_author = 1", mission_id),
        "리뷰어 코멘트가 달린 PR": _one(
            conn, "SELECT COUNT(DISTINCT pr_number) FROM comments WHERE mission_id = ? AND is_pr_author = 0",
            mission_id),
        "리뷰어": _one(
            conn, "SELECT COUNT(DISTINCT author) FROM comments WHERE mission_id = ? AND is_pr_author = 0",
            mission_id),
        "원문 링크가 없는 코멘트": _one(
            conn, "SELECT COUNT(*) FROM comments WHERE mission_id = ? AND url NOT LIKE 'https://github.com/%'",
            mission_id),
    }


def measure_topic_prs(conn: sqlite3.Connection, mission_id: str) -> dict[str, int]:
    """주제별로 지적받은 PR 수."""
    rows = conn.execute(
        "SELECT ct.topic_id, COUNT(DISTINCT c.pr_number) FROM comment_topics ct "
        "JOIN comments c ON c.id = ct.comment_id WHERE c.mission_id = ? GROUP BY ct.topic_id",
        (mission_id,),
    ).fetchall()
    return dict(rows)


def verify_mission(conn: sqlite3.Connection, mission_id: str) -> bool:
    """기준값과 비교해 표로 출력한다. 전부 맞으면 True."""
    expected = EXPECTED[mission_id]
    counts = measure_counts(conn, mission_id)
    topic_prs = measure_topic_prs(conn, mission_id)
    reviewed = counts["리뷰어 코멘트가 달린 PR"]

    def percent(topic_id: str) -> int:
        return int(f"{topic_prs.get(topic_id, 0) / reviewed * 100:.0f}") if reviewed else 0

    checks: list[tuple[str, str, object, object, bool]] = []
    for name, want in expected["counts"].items():
        checks.append(("적재", name, want, counts[name], counts[name] == want))
    for topic_id, want in expected["concept_percent"].items():
        checks.append(("개념(%)", topic_id, want, percent(topic_id), percent(topic_id) == want))
    for topic_id, want in expected["concept_percent_at_least"].items():
        checks.append(("개념(%)", topic_id, f"{want} 이상", percent(topic_id), percent(topic_id) >= want))
    for topic_id, want in expected["subtopic_prs"].items():
        got = topic_prs.get(topic_id, 0)
        checks.append(("세부(PR 수)", topic_id, want, got, got == want))

    for group, name, want, got, ok in checks:
        print(f"{'OK  ' if ok else '차이'}  {group:<10}  {name:<26}  기준 {want!s:<8}  실제 {got}")
    failed = sum(1 for check in checks if not check[4])
    print(f"\n{len(checks)}개 중 {len(checks) - failed}개 일치" + (f", {failed}개 차이" if failed else ""))
    return failed == 0
