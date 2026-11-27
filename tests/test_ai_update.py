"""새로 달리거나 고친 리뷰만 AI로 분류해 고정본에 덧붙인다 (scripts/ai_classify.py의 update).

AI 호출(call_claude)은 가짜로 바꾼다. 가짜도 진짜처럼 Budget에 호출을 잡고 비용을 남긴다.
"""

import json
import sqlite3
from pathlib import Path

import pytest

import scripts.ai_classify
from pipeline.ai_store import AiTopics, Entry, load_ai_topics, save_ai_topics
from pipeline.schema import create_schema
from pipeline.tagger import tag_mission
from pipeline.topics import CONCEPTS_VERSION
from scripts.ai_classify import PROMPT_VERSION, edited_after, update

MISSION = "java-racingcar"
COST = 0.05
SYNCED_AT = "2026-03-20T10:00:00+09:00"  # 테스트 DB의 수집 시각


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "cholog.db"
    conn = sqlite3.connect(path)
    create_schema(conn)
    conn.execute("INSERT INTO missions (id, repo, name, synced_at) VALUES (?, 'owner/repo', '테스트 미션', ?)",
                 (MISSION, SYNCED_AT))
    conn.commit()
    conn.close()
    return path


def _add(db: Path, comment_id: int, updated_at: str = "2026-03-01T00:00:00Z", body: str = "고민해 보세요",
         is_pr_author: int = 0, kind: str = "review") -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO comments (id, mission_id, pr_number, kind, author, is_pr_author, body, path, created_at, "
        "updated_at, url) VALUES (?, ?, 1, ?, 'reviewer-id', ?, ?, 'src/A.java', '2026-03-01T00:00:00Z', ?, 'u')",
        (comment_id, MISSION, kind, is_pr_author, body, updated_at),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def ai_dir(tmp_path: Path) -> Path:
    return tmp_path / "ai_topics"


@pytest.fixture
def sent(monkeypatch) -> list[int]:
    """가짜 AI. 받은 코멘트 id를 남기고, 모두 responsibility로 분류한다."""
    received: list[int] = []

    def fake_call_claude(budget, label, model, system, user, kind="call"):
        budget.acquire(kind)
        items = json.loads(user.split("\n\n", 1)[1])
        received.extend(item["id"] for item in items)
        result = {"result": json.dumps({str(item["id"]): ["responsibility"] for item in items}),
                  "total_cost_usd": COST, "modelUsage": {"claude-opus-test": {}}}
        budget.record(label, result, None, 0.1, kind)
        return result

    monkeypatch.setattr(scripts.ai_classify, "call_claude", fake_call_claude)
    return received


def _run(db: Path, ai_dir: Path, tmp_path: Path, limit: float = 10.0, **kwargs) -> dict:
    return update(MISSION, limit, db=db, directory=ai_dir, cost_log=tmp_path / "cost.json", workers=1, **kwargs)


def _save(ai_dir: Path, entries: dict) -> None:
    save_ai_topics(AiTopics(mission_id=MISSION, model="claude-opus-test", entries=entries), ai_dir)


# 3월 10일에 받은 본문을 3월 15일에 분류한 옛 항목
OLD = Entry(["naming"], "2026-03-15", "2026-03-10", "old-prompt", "old-concepts")


def test_고정본에_없는_코멘트만_보내고_기존_항목은_그대로_둔다(db, ai_dir, tmp_path, sent):
    _add(db, 1, "2026-03-05T00:00:00Z")
    _add(db, 2)
    _add(db, 3, is_pr_author=1)  # PR 작성자 본인 코멘트는 분류하지 않는다
    _save(ai_dir, {("review", 1): OLD, ("review", 99): OLD})  # 99는 DB에서 지워진 코멘트

    summary = _run(db, ai_dir, tmp_path)

    assert sent == [2]
    assert (summary["new"], summary["edited"], summary["saved"]) == (1, 0, 1)
    fixed = load_ai_topics(MISSION, ai_dir)
    assert fixed.entries[("review", 1)] == OLD
    assert fixed.entries[("review", 99)] == OLD
    added = fixed.entries[("review", 2)]
    assert added.topics == ["responsibility"]
    assert (added.prompt_version, added.concepts_version) == (PROMPT_VERSION, CONCEPTS_VERSION)
    assert "T" in added.classified_at  # 새 항목은 날짜가 아니라 시각을 남긴다
    assert added.synced_at == SYNCED_AT


def test_본문을_수집한_뒤_고친_코멘트는_다시_보내_덮어쓴다(db, ai_dir, tmp_path, sent):
    _add(db, 1, "2026-03-12T00:00:00Z")  # 분류(3월 15일)보다는 앞서지만 수집(3월 10일)보다 늦게 고쳤다
    _save(ai_dir, {("review", 1): OLD})

    summary = _run(db, ai_dir, tmp_path)

    assert sent == [1]
    assert (summary["new"], summary["edited"]) == (0, 1)
    entry = load_ai_topics(MISSION, ai_dir).entries[("review", 1)]
    assert entry.topics == ["responsibility"]
    assert entry.prompt_version == PROMPT_VERSION
    assert entry.synced_at == SYNCED_AT
    assert entry.classified_at != OLD.classified_at


def test_수집_시각이_날짜뿐이면_그날_안에_고친_것은_다시_보내지_않는다(db, ai_dir, tmp_path, sent):
    _add(db, 1, "2026-03-10T14:00:00Z")  # 한국 시간 3월 10일 23시: 수집한 날과 같은 날
    _add(db, 2, "2026-03-10T16:00:00Z")  # 한국 시간 3월 11일 1시: 다음 날
    _save(ai_dir, {("review", 1): OLD, ("review", 2): OLD})

    _run(db, ai_dir, tmp_path)

    assert sent == [2]


def test_고친_시각은_수집_시각과_초_단위로_비교한다():
    assert edited_after("2026-03-10T05:00:01Z", "2026-03-10T14:00:00+09:00")
    assert not edited_after("2026-03-10T05:00:00Z", "2026-03-10T14:00:00+09:00")


def test_다시_실행하면_이미_분류한_코멘트는_보내지_않는다(db, ai_dir, tmp_path, sent):
    _add(db, 1)
    _add(db, 2)
    _run(db, ai_dir, tmp_path)
    first = load_ai_topics(MISSION, ai_dir)
    sent.clear()

    summary = _run(db, ai_dir, tmp_path)

    assert sent == []
    assert (summary["new"], summary["edited"]) == (0, 0)
    assert load_ai_topics(MISSION, ai_dir) == first


def test_비용_상한에_닿으면_멈추고_다시_실행하면_남은_코멘트만_보낸다(db, ai_dir, tmp_path, sent, monkeypatch):
    monkeypatch.setattr(scripts.ai_classify, "BATCH", 1)
    for comment_id in range(1, 6):
        _add(db, comment_id)

    # 상한 0.2의 90%는 0.18. 0.05짜리 호출은 세 번까지 보내고(누적 0.15) 네 번째는 보내지 않는다.
    summary = _run(db, ai_dir, tmp_path, limit=0.2)

    assert sent == [1, 2, 3]
    assert (summary["saved"], summary["stopped"]) == (3, 2)
    assert set(load_ai_topics(MISSION, ai_dir).entries) == {("review", 1), ("review", 2), ("review", 3)}

    sent.clear()
    _run(db, ai_dir, tmp_path, limit=1.0)

    assert sent == [4, 5]
    cost = json.loads((tmp_path / "cost.json").read_text())["steps"][f"update:{MISSION}"]
    assert cost["total_usd"] == pytest.approx(COST * 5)


def test_고정본이_없는_미션은_모든_코멘트를_보내_새로_만든다(db, ai_dir, tmp_path, sent):
    _add(db, 1)
    _add(db, 2, kind="issue")

    _run(db, ai_dir, tmp_path)

    assert sorted(sent) == [1, 2]
    fixed = load_ai_topics(MISSION, ai_dir)
    assert set(fixed.entries) == {("review", 1), ("issue", 2)}
    assert fixed.model == "claude-opus-test"


def test_수집하는_중에_고친_코멘트는_다시_실행해도_또_보내지_않는다(db, ai_dir, tmp_path, sent):
    _add(db, 1, "2026-03-20T02:00:00Z")  # 한국 시간 11시: 수집을 시작한 10시보다 늦다. DB의 본문이 이미 수정본이다
    _run(db, ai_dir, tmp_path)
    assert load_ai_topics(MISSION, ai_dir).entries[("review", 1)].synced_at == "2026-03-20T02:00:00Z"
    sent.clear()

    _run(db, ai_dir, tmp_path)

    assert sent == []


def test_DB에_수집_시각이_없으면_멈춘다(db, ai_dir, tmp_path, sent):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE missions SET synced_at = NULL")
    conn.commit()
    conn.close()
    _add(db, 1)

    with pytest.raises(SystemExit, match="synced_at"):
        _run(db, ai_dir, tmp_path)
    assert sent == []


def test_dry_run은_AI를_부르지_않고_대상_수만_센다(db, ai_dir, tmp_path, sent):
    _add(db, 1, "2026-03-12T00:00:00Z")  # 고친 코멘트
    _add(db, 2)  # 새 코멘트
    _add(db, 3)  # 옛 버전 코멘트
    _add(db, 4)  # 지금 버전 코멘트
    current = Entry([], "2026-03-15", "2026-03-10", PROMPT_VERSION, CONCEPTS_VERSION)
    _save(ai_dir, {("review", 1): OLD, ("review", 3): OLD, ("review", 4): current})
    before = (ai_dir / f"{MISSION}.json").read_text()

    summary = update(MISSION, None, dry_run=True, db=db, directory=ai_dir, cost_log=tmp_path / "cost.json")

    assert sent == []
    assert (summary["new"], summary["edited"], summary["stale"]) == (1, 1, 1)
    assert (ai_dir / f"{MISSION}.json").read_text() == before
    assert not (tmp_path / "cost.json").exists()


def test_update로_덧붙인_코멘트는_ai로_남은_코멘트는_키워드로_붙는다(db, ai_dir, tmp_path, sent, monkeypatch):
    monkeypatch.setattr(scripts.ai_classify, "BATCH", 1)
    _add(db, 1, body="이 클래스가 하는 일이 너무 많아 보여요")  # 키워드에는 안 걸린다
    _add(db, 2, body="책임을 나눠 보세요")  # 상한에 막혀 분류하지 못한다. 키워드에 걸린다
    _run(db, ai_dir, tmp_path, limit=COST * 2)  # 90%가 0.09라 호출 하나만 보낸다
    assert sent == [1]

    conn = sqlite3.connect(db)
    tag_mission(conn, MISSION, ai_dir)

    assert set(conn.execute("SELECT comment_id, topic_id, method FROM comment_topics")) == {
        (1, "responsibility", "ai"),
        (2, "responsibility", "keyword"),
    }
    conn.close()
