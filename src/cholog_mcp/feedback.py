"""반복 지적된 주제를 세는 도구 로직.

DB 연결을 받아 결과를 만들 뿐, MCP나 실행 방식(stdio, HTTP)은 모른다.
리뷰가 어떤 방법으로 분류됐는지도 모른다. comment_topics 테이블만 읽는다.
"""

import re
import sqlite3
from datetime import date

EXCERPT_MAX_LENGTH = 300
EXAMPLE_MIN_LENGTH = 30

KEYWORD_NOTE = "키워드로 센 값이라 실제보다 적게 잡힌다. 주제가 붙지 않은 리뷰가 {untagged}개 있다."
DEFAULT_NOTE = "주제가 붙지 않은 리뷰가 {untagged}개 있다."

_QUOTE_LINE = re.compile(r"^\s*>.*$", re.MULTILINE)
_BLANK_LINES = re.compile(r"\n\s*\n+")
_SPACES = re.compile(r"[ \t]{2,}")
_AUTHOR_SEPARATOR = re.compile(r"[\s,]+")


def get_repeated_feedback(
    conn: sqlite3.Connection,
    mission: str,
    authors: list[str] | None = None,
    since: date | None = None,
    max_topics: int = 8,
    examples_per_topic: int = 2,
) -> dict:
    """미션에서 리뷰어들이 반복 지적한 주제를 많은 순으로 돌려준다. 형태는 docs/tool-spec.md 3번."""
    mission_row = conn.execute("SELECT synced_at FROM missions WHERE id = ?", (mission,)).fetchone()
    if mission_row is None:
        raise ValueError(f"데이터가 없는 미션이다: {mission}")

    requested = _normalize_authors(authors)
    prs = _find_prs(conn, mission, requested, since)
    pr_numbers = [number for number, _ in prs]
    found_authors = {author.lower() for _, author in prs if author}

    stats = _count_scope(conn, mission, pr_numbers)
    # 범위를 좁혔을 때만 미션 전체와 비교한다.
    overall = _count_scope(conn, mission, None) if requested else None

    names = {
        topic_id: (parent_id, name)
        for topic_id, parent_id, name in conn.execute("SELECT id, parent_id, name FROM topics")
    }
    concepts = sorted(
        (topic_id for topic_id in stats.topic_prs if names[topic_id][0] is None),
        key=lambda topic_id: (-stats.topic_prs[topic_id], -stats.topic_comments[topic_id], topic_id),
    )[:max_topics]

    topics = []
    example_prs: set[int] = set()
    for topic_id in concepts:
        examples = _pick_examples(conn, mission, pr_numbers, topic_id, examples_per_topic, example_prs)
        example_prs.update(example["pr"] for example in examples)
        topics.append({
            "id": topic_id,
            "name": names[topic_id][1],
            "pr_count": stats.topic_prs[topic_id],
            "pr_ratio": _ratio(stats.topic_prs[topic_id], stats.reviewed_prs),
            "comment_count": stats.topic_comments[topic_id],
            "overall_pr_ratio": _ratio(overall.topic_prs.get(topic_id, 0), overall.reviewed_prs) if overall else None,
            "subtopics": [
                {"id": sub_id, "name": names[sub_id][1], "pr_count": stats.topic_prs[sub_id]}
                for sub_id in sorted(stats.topic_prs, key=lambda sub_id: (-stats.topic_prs[sub_id], sub_id))
                if names[sub_id][0] == topic_id
            ],
            "examples": examples,
        })

    return {
        "scope": {
            "mission": mission,
            "authors_requested": len(requested),
            "authors_not_found": [author for author in requested if author.lower() not in found_authors],
            "pr_count": len(prs),
            "reviewed_pr_count": stats.reviewed_prs,
            "reviewer_comment_count": stats.reviewer_comments,
            "data_as_of": mission_row[0],
        },
        "counting": _describe_counting(conn, mission, stats.untagged_comments),
        "topics": topics,
    }


class _ScopeStats:
    """PR 범위 안에서 센 값."""

    def __init__(self, conn: sqlite3.Connection, where: str, params: list) -> None:
        self.reviewed_prs, self.reviewer_comments = conn.execute(
            f"SELECT COUNT(DISTINCT c.pr_number), COUNT(*) FROM comments c WHERE {where}", params
        ).fetchone()
        self.untagged_comments = conn.execute(
            f"SELECT COUNT(*) FROM comments c WHERE {where} "
            "AND NOT EXISTS (SELECT 1 FROM comment_topics ct WHERE ct.comment_id = c.id)",
            params,
        ).fetchone()[0]
        self.topic_prs: dict[str, int] = {}
        self.topic_comments: dict[str, int] = {}
        rows = conn.execute(
            "SELECT ct.topic_id, COUNT(DISTINCT c.pr_number), COUNT(*) FROM comment_topics ct "
            f"JOIN comments c ON c.id = ct.comment_id WHERE {where} GROUP BY ct.topic_id",
            params,
        )
        for topic_id, pr_count, comment_count in rows:
            self.topic_prs[topic_id] = pr_count
            self.topic_comments[topic_id] = comment_count


def _reviewer_comments_in(mission: str, pr_numbers: list[int] | None) -> tuple[str, list]:
    """리뷰어 코멘트만 고르는 WHERE 조건. pr_numbers가 None이면 미션 전체."""
    where = "c.mission_id = ? AND c.is_pr_author = 0"
    params: list = [mission]
    if pr_numbers is not None:
        where += f" AND c.pr_number IN ({', '.join('?' * len(pr_numbers))})"
        params += pr_numbers
    return where, params


def _count_scope(conn: sqlite3.Connection, mission: str, pr_numbers: list[int] | None) -> _ScopeStats:
    where, params = _reviewer_comments_in(mission, pr_numbers)
    return _ScopeStats(conn, where, params)


def _normalize_authors(authors: list[str] | None) -> list[str]:
    """@를 떼고, 대소문자만 다른 중복을 없앤다.

    GitHub ID에는 공백과 쉼표가 올 수 없으므로, 한 문자열에 여러 ID가 들어오면 나눈다.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for author in _AUTHOR_SEPARATOR.split(" ".join(authors or [])):
        author = author.lstrip("@")
        if author and author.lower() not in seen:
            seen.add(author.lower())
            normalized.append(author)
    return normalized


def _find_prs(
    conn: sqlite3.Connection, mission: str, authors: list[str], since: date | None
) -> list[tuple[int, str | None]]:
    where = "mission_id = ?"
    params: list = [mission]
    if authors:
        where += f" AND LOWER(author) IN ({', '.join('?' * len(authors))})"
        params += [author.lower() for author in authors]
    if since is not None:
        where += " AND created_at >= ?"
        params.append(since.isoformat())
    return conn.execute(f"SELECT number, author FROM pull_requests WHERE {where} ORDER BY number", params).fetchall()


def _pick_examples(
    conn: sqlite3.Connection,
    mission: str,
    pr_numbers: list[int],
    topic_id: str,
    limit: int,
    used_elsewhere: set[int],
) -> list[dict]:
    """서로 다른 PR에서 하나씩, 관련도(score)가 큰 순으로 고른다.

    여러 주제의 대표 리뷰가 몇몇 PR에 몰리지 않도록, 다른 주제에서 아직 쓰지 않은 PR을 먼저 고른다.
    """
    if limit == 0:
        return []
    where, params = _reviewer_comments_in(mission, pr_numbers)
    rows = conn.execute(
        "SELECT c.pr_number, pr.author, c.author, c.path, c.body, c.url FROM comment_topics ct "
        "JOIN comments c ON c.id = ct.comment_id "
        "JOIN pull_requests pr ON pr.mission_id = c.mission_id AND pr.number = c.pr_number "
        f"WHERE {where} AND ct.topic_id = ? "
        "AND LENGTH(TRIM(c.body)) >= ? ORDER BY ct.score DESC, c.id",
        [*params, topic_id, EXAMPLE_MIN_LENGTH],
    )
    # PR마다 관련도가 가장 큰 리뷰 하나만 남긴다. 순서는 관련도가 큰 순이다.
    best_per_pr: dict[int, dict] = {}
    for pr_number, author, reviewer, path, body, url in rows:
        best_per_pr.setdefault(pr_number, {
            "pr": pr_number,
            "author": author,
            "reviewer": reviewer,
            "path": path,
            "excerpt": _excerpt(body),
            "url": url,
        })
    fresh = [example for pr_number, example in best_per_pr.items() if pr_number not in used_elsewhere]
    reused = [example for pr_number, example in best_per_pr.items() if pr_number in used_elsewhere]
    return (fresh + reused)[:limit]


def _excerpt(body: str) -> str:
    """리뷰어 자신의 말만 앞에서부터 자른다. 인용한 줄(>)은 빼고 빈 줄과 이어진 공백은 하나로 줄인다."""
    body = _QUOTE_LINE.sub("", body.replace("\r\n", "\n"))
    body = _SPACES.sub(" ", _BLANK_LINES.sub("\n\n", body)).strip()
    if len(body) <= EXCERPT_MAX_LENGTH:
        return body
    return body[: EXCERPT_MAX_LENGTH - 1] + "…"


def _describe_counting(conn: sqlite3.Connection, mission: str, untagged: int) -> dict:
    methods = [
        method
        for (method,) in conn.execute(
            "SELECT DISTINCT ct.method FROM comment_topics ct JOIN comments c ON c.id = ct.comment_id "
            "WHERE c.mission_id = ? ORDER BY ct.method",
            (mission,),
        )
    ]
    method = "+".join(methods) if methods else None
    note = KEYWORD_NOTE if method == "keyword" else DEFAULT_NOTE
    return {
        "method": method,
        "untagged_comment_count": untagged,
        "note": note.format(untagged=untagged),
    }


def _ratio(count: int, total: int) -> float:
    return round(count / total, 2) if total else 0.0
