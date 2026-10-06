"""리뷰어 코멘트에 주제를 붙인다 (키워드 방식).

결과는 comment_topics 테이블에만 쓴다. 도구는 그 테이블만 읽으므로,
분류 방법을 바꿔도 도구 코드는 바뀌지 않는다.
"""

import re
import sqlite3

from pipeline.topics import CONCEPTS, SUBTOPICS

METHOD = "keyword"

_NOISE = (
    re.compile(r"```.*?```", re.DOTALL),  # 코드 블록
    re.compile(r"`[^`]*`"),  # 인라인 코드
    re.compile(r"^\s*>.*$", re.MULTILINE),  # 인용
    re.compile(r"https?://\S+"),  # 링크
    re.compile(r"<img[^>]*>"),  # 이미지
)


def clean(body: str) -> str:
    """키워드와 상관없는 부분(코드, 인용, 링크)을 지우고 소문자로 바꾼다."""
    for noise in _NOISE:
        body = noise.sub(" ", body)
    return body.lower()


def tag_body(body: str, mission_id: str) -> dict[str, int]:
    """코멘트 본문에 붙는 주제와 관련도(키워드가 걸린 횟수)를 돌려준다."""
    scores: dict[str, int] = {}

    cleaned = clean(body)
    for concept in CONCEPTS:
        hits = sum(cleaned.count(keyword) for keyword in concept.keywords)
        if hits:
            scores[concept.id] = hits

    for subtopic in SUBTOPICS:
        if subtopic.mission_id != mission_id or not subtopic.gate.search(body):
            continue
        hits = sum(1 for _ in subtopic.pattern.finditer(body))
        if hits:
            scores[subtopic.id] = hits
            # 세부 지적이 붙으면 그 개념도 붙인다.
            scores[subtopic.parent_id] = max(scores.get(subtopic.parent_id, 0), hits)

    return scores


def sync_topics(conn: sqlite3.Connection) -> None:
    """주제 사전을 topics 테이블에 반영한다."""
    conn.executemany(
        "INSERT INTO topics (id, parent_id, mission_id, name) VALUES (?, NULL, NULL, ?) "
        "ON CONFLICT (id) DO UPDATE SET name = excluded.name",
        [(concept.id, concept.name) for concept in CONCEPTS],
    )
    conn.executemany(
        "INSERT INTO topics (id, parent_id, mission_id, name) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET parent_id = excluded.parent_id, "
        "mission_id = excluded.mission_id, name = excluded.name",
        [(s.id, s.parent_id, s.mission_id, s.name) for s in SUBTOPICS],
    )


def tag_mission(conn: sqlite3.Connection, mission_id: str) -> int:
    """미션의 리뷰어 코멘트를 다시 분류한다. 붙인 주제 수를 돌려준다."""
    with conn:
        sync_topics(conn)
        conn.execute(
            "DELETE FROM comment_topics WHERE method = ? AND comment_id IN "
            "(SELECT id FROM comments WHERE mission_id = ?)",
            (METHOD, mission_id),
        )
        rows = conn.execute(
            "SELECT id, body FROM comments WHERE mission_id = ? AND is_pr_author = 0",
            (mission_id,),
        ).fetchall()
        tags = [
            (comment_id, topic_id, METHOD, score)
            for comment_id, body in rows
            for topic_id, score in tag_body(body, mission_id).items()
        ]
        conn.executemany(
            "INSERT INTO comment_topics (comment_id, topic_id, method, score) VALUES (?, ?, ?, ?)",
            tags,
        )
    return len(tags)
