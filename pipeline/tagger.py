"""리뷰어 코멘트에 주제를 붙인다.

AI 분류 고정본(pipeline/ai_topics/<mission>.json)이 있으면 그 주제를 붙이고(method='ai'),
고정본에 없는 코멘트(고정본을 만든 뒤 새로 달린 리뷰)만 키워드로 붙인다(method='keyword').
정규식 세부 지적은 고정본이 있어도 계속 돌린다.

결과는 comment_topics 테이블에만 쓴다. 도구는 그 테이블만 읽으므로,
분류 방법을 바꿔도 도구 코드는 바뀌지 않는다.
"""

import re
import sqlite3
from pathlib import Path

from pipeline.ai_store import AI_TOPICS_DIR, load_ai_topics
from pipeline.topics import CONCEPTS, SUBTOPICS

METHOD = "keyword"
METHOD_AI = "ai"

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
    scores = tag_subtopics(body, mission_id)

    cleaned = clean(body)
    for concept in CONCEPTS:
        hits = sum(cleaned.count(keyword) for keyword in concept.keywords)
        if hits:
            scores[concept.id] = max(scores.get(concept.id, 0), hits)

    return scores


def tag_subtopics(body: str, mission_id: str) -> dict[str, int]:
    """정규식이 있는 세부 지적만 본다. 붙은 세부 지적과 그 개념을 돌려준다."""
    scores: dict[str, int] = {}
    for subtopic in SUBTOPICS:
        if subtopic.mission_id != mission_id or subtopic.gate is None or subtopic.pattern is None:
            continue
        if not subtopic.gate.search(body):
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


def _github_id_column(conn: sqlite3.Connection) -> str:
    """GitHub 코멘트 ID가 든 열. github_id 열이 없는 스키마에서는 id가 곧 GitHub ID다."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)")}
    return "github_id" if "github_id" in columns else "id"


def _with_parents(topic_ids: list[str]) -> list[str]:
    """세부 지적이 붙으면 그 개념도 붙인다. 사전에 없는 id는 받지 않는다."""
    parents = {subtopic.id: subtopic.parent_id for subtopic in SUBTOPICS}
    known = {concept.id for concept in CONCEPTS} | set(parents)
    unknown = sorted(set(topic_ids) - known)
    if unknown:
        raise ValueError(f"AI 고정본에 주제 사전에 없는 id가 있다: {unknown}")
    return sorted(set(topic_ids) | {parents[t] for t in topic_ids if t in parents})


def tag_mission(conn: sqlite3.Connection, mission_id: str, ai_dir: Path = AI_TOPICS_DIR) -> int:
    """미션의 리뷰어 코멘트를 다시 분류한다. 붙인 주제 수를 돌려준다."""
    ai_topics = load_ai_topics(mission_id, ai_dir)
    fixed = ai_topics.topics if ai_topics else {}
    with conn:
        sync_topics(conn)
        conn.execute(
            "DELETE FROM comment_topics WHERE method IN (?, ?) AND comment_id IN "
            "(SELECT id FROM comments WHERE mission_id = ?)",
            (METHOD, METHOD_AI, mission_id),
        )
        rows = conn.execute(
            f"SELECT id, kind, {_github_id_column(conn)}, body FROM comments "
            "WHERE mission_id = ? AND is_pr_author = 0",
            (mission_id,),
        ).fetchall()
        tags = []
        for comment_id, kind, github_id, body in rows:
            if (kind, github_id) not in fixed:
                tags.extend((comment_id, t, METHOD, score) for t, score in tag_body(body, mission_id).items())
                continue
            ai = _with_parents(fixed[(kind, github_id)])
            tags.extend((comment_id, t, METHOD_AI, 1) for t in ai)
            # 정규식 세부 지적은 고정본이 있어도 돌린다. AI가 이미 붙인 주제는 한 번만 넣는다.
            tags.extend(
                (comment_id, t, METHOD, score)
                for t, score in tag_subtopics(body, mission_id).items() if t not in ai
            )
        conn.executemany(
            "INSERT INTO comment_topics (comment_id, topic_id, method, score) VALUES (?, ?, ?, ?)",
            tags,
        )
    return len(tags)
