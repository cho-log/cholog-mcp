"""AI 분류 고정본을 읽어 주제를 붙이는 규칙."""

import json
import sqlite3
from pathlib import Path

import pytest

import pipeline.tagger
from cholog_mcp.missions import Mission
from pipeline.ai_store import AiTopics, Entry, ai_topics_path, load_ai_topics, save_ai_topics
from pipeline.load import load_mission
from pipeline.schema import create_schema
from pipeline.tagger import tag_mission
from pipeline.topics import SUBTOPICS, Subtopic

MISSION = Mission(id="java-racingcar", repo="owner/repo", name="테스트 미션")


def _ai_topics(topics: dict[tuple[str, int], list[str]]) -> AiTopics:
    return AiTopics(
        mission_id=MISSION.id,
        model="test-model",
        entries={key: Entry(ids, "2026-11-20", "2026-11-19T10:00:00+09:00", "test", "test") for key, ids in topics.items()},
    )


def _comment(comment_id: int, login: str, body: str) -> dict:
    return {
        "id": comment_id,
        "user": {"login": login},
        "body": body,
        "created_at": "2026-03-01T00:00:00Z",
        "updated_at": "2026-03-02T00:00:00Z",
        "html_url": f"https://github.com/owner/repo/pull/1#discussion_r{comment_id}",
    }


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    (raw / "review").mkdir(parents=True)
    (raw / "issue").mkdir()
    prs = [{"number": 1, "author": {"login": "learner"}, "title": "미션 제출", "createdAt": "2026-03-01T00:00:00Z"}]
    (raw / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    review = [
        _comment(10, "reviewer", "이 클래스가 하는 일이 너무 많아 보여요"),  # 키워드에는 안 걸린다
        _comment(11, "reviewer", "책임을 나눠 보세요"),  # 키워드에 걸린다
        _comment(12, "learner", "고쳤습니다"),
    ]
    (raw / "review" / "1.json").write_text(json.dumps(review), encoding="utf-8")
    (raw / "issue" / "1.json").write_text(json.dumps([_comment(20, "reviewer", "수고하셨습니다")]), encoding="utf-8")
    return raw


@pytest.fixture
def ai_dir(tmp_path: Path) -> Path:
    return tmp_path / "ai_topics"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    return conn


def _tags(conn: sqlite3.Connection) -> set[tuple[str, int, str, str]]:
    """(kind, GitHub ID, 주제, 방법). comments.id 대신 GitHub ID로 본다."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)")}
    github_id = "c.github_id" if "github_id" in columns else "c.id"
    return set(conn.execute(
        f"SELECT c.kind, {github_id}, ct.topic_id, ct.method FROM comment_topics ct "
        "JOIN comments c ON c.id = ct.comment_id"
    ))


def test_고정본은_저장한_그대로_다시_읽힌다(ai_dir):
    saved = _ai_topics({("review", 10): ["responsibility", "naming"], ("issue", 10): []})
    save_ai_topics(saved, ai_dir)

    loaded = load_ai_topics(MISSION.id, ai_dir)

    assert loaded == _ai_topics({("review", 10): ["naming", "responsibility"], ("issue", 10): []})


def test_고정본에는_리뷰_원문을_넣지_않는다(ai_dir):
    path = save_ai_topics(_ai_topics({("review", 10): ["responsibility"]}), ai_dir)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"mission_id", "model", "topics"}
    assert data["topics"] == {"review:10": {
        "topics": ["responsibility"], "classified_at": "2026-11-20", "synced_at": "2026-11-19T10:00:00+09:00",
        "prompt_version": "test", "concepts_version": "test",
    }}


def test_고정본은_코멘트_하나를_한_줄에_쓴다(ai_dir):
    path = save_ai_topics(_ai_topics({("review", 10): ["responsibility"], ("review", 11): []}), ai_dir)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert sum('"review:10"' in line for line in lines) == 1
    assert any('"review:10"' in line and '"classified_at"' in line and '"concepts_version"' in line for line in lines)


def test_버전이_파일_머리에만_있는_옛_고정본은_머리의_값을_각_코멘트에_붙여_읽는다(ai_dir):
    old = {
        "mission_id": MISSION.id, "classified_at": "2026-11-12", "model": "test-model",
        "prompt_version": "p1", "concepts_version": "c1",
        "topics": {"review:10": ["responsibility", "naming"], "issue:20": []},
    }
    ai_topics_path(MISSION.id, ai_dir).parent.mkdir(parents=True)
    ai_topics_path(MISSION.id, ai_dir).write_text(json.dumps(old), encoding="utf-8")

    loaded = load_ai_topics(MISSION.id, ai_dir)

    assert loaded.topics == {("review", 10): ["responsibility", "naming"], ("issue", 20): []}
    # 옛 형식에는 수집 시각이 없어서 분류한 날로 둔다.
    assert all((e.classified_at, e.synced_at, e.prompt_version, e.concepts_version) == ("2026-11-12", "2026-11-12", "p1", "c1")
               for e in loaded.entries.values())


def test_고정본이_없으면_None(ai_dir):
    assert load_ai_topics(MISSION.id, ai_dir) is None


def test_고정본의_주제는_ai로_붙고_고정본에_없는_코멘트만_키워드로_붙는다(raw_dir, ai_dir):
    conn = _conn()
    load_mission(conn, MISSION, raw_dir)
    # review 11은 고정본을 만든 뒤 새로 달린 리뷰라고 본다. issue 20은 AI가 주제 없음으로 본 코멘트다.
    save_ai_topics(_ai_topics({("review", 10): ["responsibility"], ("issue", 20): []}), ai_dir)

    tag_mission(conn, MISSION.id, ai_dir)

    assert _tags(conn) == {
        ("review", 10, "responsibility", "ai"),
        ("review", 11, "responsibility", "keyword"),
    }


def test_고정본이_없으면_전부_키워드로_붙는다(raw_dir, ai_dir):
    conn = _conn()
    load_mission(conn, MISSION, raw_dir)

    tag_mission(conn, MISSION.id, ai_dir)

    assert _tags(conn) == {("review", 11, "responsibility", "keyword")}


def test_정규식_세부_지적은_고정본이_있어도_붙는다(tmp_path, ai_dir):
    raw = tmp_path / "raw2"
    (raw / "review").mkdir(parents=True)
    prs = [{"number": 1, "author": {"login": "learner"}, "title": "미션 제출", "createdAt": "2026-03-01T00:00:00Z"}]
    (raw / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    (raw / "review" / "1.json").write_text(
        json.dumps([_comment(10, "reviewer", "난수 생성기를 상속해서 테스트하셨네요")]), encoding="utf-8")
    conn = _conn()
    load_mission(conn, MISSION, raw)
    save_ai_topics(_ai_topics({("review", 10): ["test-writing"]}), ai_dir)

    tag_mission(conn, MISSION.id, ai_dir)

    assert _tags(conn) == {
        ("review", 10, "test-writing", "ai"),
        ("review", 10, "random-inherit", "keyword"),
        ("review", 10, "testability-random", "keyword"),
    }


def test_정규식_없는_세부_지적도_고정본으로_붙고_개념이_함께_붙는다(raw_dir, ai_dir, monkeypatch):
    ai_only = Subtopic("ai-only-subtopic", "AI로만 붙는 세부 지적", "responsibility", MISSION.id)
    monkeypatch.setattr(pipeline.tagger, "SUBTOPICS", (*SUBTOPICS, ai_only))
    conn = _conn()
    load_mission(conn, MISSION, raw_dir)
    save_ai_topics(_ai_topics({("review", 10): ["ai-only-subtopic"]}), ai_dir)

    tag_mission(conn, MISSION.id, ai_dir)

    assert ("review", 10, "ai-only-subtopic", "ai") in _tags(conn)
    assert ("review", 10, "responsibility", "ai") in _tags(conn)
    assert conn.execute("SELECT parent_id FROM topics WHERE id = 'ai-only-subtopic'").fetchone() == ("responsibility",)


def test_정규식_없는_세부_지적은_키워드로는_붙지_않는다(raw_dir, ai_dir, monkeypatch):
    ai_only = Subtopic("ai-only-subtopic", "AI로만 붙는 세부 지적", "responsibility", MISSION.id)
    monkeypatch.setattr(pipeline.tagger, "SUBTOPICS", (*SUBTOPICS, ai_only))
    conn = _conn()
    load_mission(conn, MISSION, raw_dir)

    tag_mission(conn, MISSION.id, ai_dir)

    assert all(topic != "ai-only-subtopic" for _, _, topic, _ in _tags(conn))


def test_사전에_없는_주제가_고정본에_있으면_멈춘다(raw_dir, ai_dir):
    conn = _conn()
    load_mission(conn, MISSION, raw_dir)
    save_ai_topics(_ai_topics({("review", 10): ["no-such-topic"]}), ai_dir)

    with pytest.raises(ValueError, match="no-such-topic"):
        tag_mission(conn, MISSION.id, ai_dir)


def test_다시_적재해도_고정본의_연결이_유지된다(raw_dir, ai_dir):
    conn = _conn()
    # ("review", 20)은 없는 코멘트다. GitHub ID가 같아도 kind가 다르면 다른 코멘트로 본다.
    topics = {("review", 10): ["responsibility"], ("issue", 20): ["naming"], ("review", 20): ["encapsulation"]}
    save_ai_topics(_ai_topics(topics), ai_dir)
    load_mission(conn, MISSION, raw_dir)
    tag_mission(conn, MISSION.id, ai_dir)
    before = _tags(conn)

    load_mission(conn, MISSION, raw_dir)
    assert _tags(conn) == set()  # 적재하면 주제가 지워진다
    tag_mission(conn, MISSION.id, ai_dir)

    assert _tags(conn) == before == {
        ("review", 10, "responsibility", "ai"),
        ("issue", 20, "naming", "ai"),
        ("review", 11, "responsibility", "keyword"),
    }
