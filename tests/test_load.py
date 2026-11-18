"""원본 적재와 SQLite 스키마 검증."""

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.load import load_mission, read_json_arrays
from cholog_mcp.missions import Mission
from pipeline.schema import SCHEMA, create_schema

MISSION = Mission(id="test-mission", repo="owner/repo", name="테스트 미션")


def _comment(comment_id: int, login: str, body: str, **extra) -> dict:
    return {
        "id": comment_id,
        "user": {"login": login},
        "body": body,
        "created_at": "2026-03-01T00:00:00Z",
        "updated_at": "2026-03-02T00:00:00Z",
        "html_url": f"https://github.com/owner/repo/pull/1#discussion_r{comment_id}",
        **extra,
    }


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    (tmp_path / "review").mkdir()
    (tmp_path / "issue").mkdir()
    prs = [
        {"number": 1, "author": {"login": "learner"}, "title": "[스터디] 미션 제출", "createdAt": "2026-03-01T00:00:00Z"},
        {"number": 2, "author": {"login": "other"}, "title": "리뷰 없는 PR", "createdAt": "2026-03-01T00:00:00Z"},
    ]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    # gh api --paginate처럼 배열 두 개를 이어 붙인다.
    review_pages = [
        [_comment(10, "reviewer", "책임을 나눠 보세요", path="Car.java", diff_hunk="@@ -1 +1 @@")],
        [_comment(11, "learner", "고쳤습니다", path="Car.java", diff_hunk="@@ -1 +1 @@")],
    ]
    (tmp_path / "review" / "1.json").write_text("".join(json.dumps(page) for page in review_pages), encoding="utf-8")
    (tmp_path / "issue" / "1.json").write_text(json.dumps([_comment(20, "reviewer", "수고하셨습니다")]), encoding="utf-8")
    (tmp_path / "meta.json").write_text(json.dumps({"fetched_at": "2026-03-03T09:00:00+09:00"}), encoding="utf-8")
    return tmp_path


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    return conn


def test_PR과_코멘트를_넣는다(conn, raw_dir):
    loaded = load_mission(conn, MISSION, raw_dir)

    assert loaded == {"pull_requests": 2, "comments": 3}
    assert conn.execute("SELECT number, author, url FROM pull_requests ORDER BY number").fetchall() == [
        (1, "learner", "https://github.com/owner/repo/pull/1"),
        (2, "other", "https://github.com/owner/repo/pull/2"),
    ]


def test_PR_작성자_본인의_코멘트를_표시한다(conn, raw_dir):
    load_mission(conn, MISSION, raw_dir)

    rows = conn.execute("SELECT github_id, kind, author, is_pr_author FROM comments ORDER BY github_id").fetchall()
    assert rows == [(10, "review", "reviewer", 0), (11, "review", "learner", 1), (20, "issue", "reviewer", 0)]


def test_원문_링크와_수집_시각을_남긴다(conn, raw_dir):
    load_mission(conn, MISSION, raw_dir)

    assert conn.execute("SELECT url FROM comments WHERE github_id = 10").fetchone()[0].endswith("#discussion_r10")
    assert conn.execute("SELECT synced_at FROM missions").fetchone()[0] == "2026-03-03T09:00:00+09:00"


def test_다시_넣으면_통째로_바뀐다(conn, raw_dir):
    load_mission(conn, MISSION, raw_dir)
    load_mission(conn, MISSION, raw_dir)

    assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 3


def test_이어_붙은_배열과_없는_파일을_읽는다(raw_dir):
    assert [c["id"] for c in read_json_arrays(raw_dir / "review" / "1.json")] == [10, 11]
    assert read_json_arrays(raw_dir / "review" / "2.json") == []


def test_부모_ID_원문과_종류별_ID_충돌을_재적재해도_보존한다(review_conn, review_raw):
    from cholog_mcp.missions import MISSIONS
    from pipeline.tagger import tag_mission
    from cholog_mcp.feedback import get_repeated_feedback

    mission = MISSIONS["java-racingcar"]
    original = review_conn.execute(
        "SELECT github_id,kind,body,url,created_at,updated_at,in_reply_to_id FROM comments ORDER BY kind,github_id"
    ).fetchall()
    tag_mission(review_conn, mission.id)
    before = get_repeated_feedback(review_conn, mission.id)
    load_mission(review_conn, mission, review_raw)
    load_mission(review_conn, mission, review_raw)
    assert review_conn.execute(
        "SELECT github_id,kind,body,url,created_at,updated_at,in_reply_to_id FROM comments ORDER BY kind,github_id"
    ).fetchall() == original
    assert review_conn.execute("SELECT COUNT(*) FROM comments WHERE github_id=10").fetchone()[0] == 2
    assert review_conn.execute("SELECT COUNT(*) FROM comment_topics").fetchone()[0] == 0
    tag_mission(review_conn, mission.id)
    assert get_repeated_feedback(review_conn, mission.id) == before
    assert review_conn.execute("SELECT in_reply_to_id FROM comments WHERE github_id=11").fetchone() == (10,)
    assert review_conn.execute("SELECT in_reply_to_id FROM comments WHERE kind='issue'").fetchall() == [(None,), (None,)]


def test_issue의_부모_필드는_무시하고_탈퇴한_작성자도_보존한다(conn, raw_dir):
    (raw_dir / "issue/1.json").write_text(json.dumps([
        _comment(20, "reviewer-id", "원문", user=None, in_reply_to_id=10)
    ]))
    load_mission(conn, MISSION, raw_dir)
    assert conn.execute("SELECT author,in_reply_to_id FROM comments WHERE kind='issue'").fetchone() == (None, None)


def test_실패한_재적재는_원문과_분류_및_다른_미션을_보존한다(conn, raw_dir):
    load_mission(conn, MISSION, raw_dir)
    conn.execute("INSERT INTO missions VALUES ('another','owner/other','다른 미션',NULL)")
    conn.execute("INSERT INTO topics VALUES ('topic',NULL,NULL,'주제')")
    key = conn.execute("SELECT id FROM comments WHERE github_id=10").fetchone()[0]
    conn.execute("INSERT INTO comment_topics VALUES (?,'topic','keyword',1)", (key,))
    conn.commit()
    original = conn.execute("SELECT * FROM comments ORDER BY id").fetchall()
    # 같은 종류의 같은 원본 ID 두 개는 실제 적재 오류다.
    (raw_dir / "review/1.json").write_text(json.dumps([_comment(10, "reviewer-id", "새 원문")] * 2))
    with pytest.raises(ValueError, match="식별자"):
        load_mission(conn, MISSION, raw_dir)
    assert conn.execute("SELECT * FROM comments ORDER BY id").fetchall() == original
    assert conn.execute("SELECT * FROM comment_topics").fetchall() == [(key, "topic", "keyword", 1)]
    assert conn.execute("SELECT COUNT(*) FROM missions WHERE id='another'").fetchone()[0] == 1


def test_내부_키로_바꿔도_대표_리뷰의_동점_선정은_원본_ID_순이다(conn, raw_dir):
    from cholog_mcp.feedback import get_repeated_feedback
    from pipeline.tagger import tag_mission

    body = "책임을 나누면 어떤 장점과 단점이 있을지 함께 생각해 보세요."
    (raw_dir / "review/1.json").write_text(json.dumps([_comment(90, "reviewer-id", body)]))
    (raw_dir / "review/2.json").write_text(json.dumps([_comment(5, "reviewer-id", body)]))
    load_mission(conn, MISSION, raw_dir)
    tag_mission(conn, MISSION.id)
    result = get_repeated_feedback(conn, MISSION.id, examples_per_topic=1)
    assert result["topics"][0]["examples"][0]["pr"] == 2


def test_미션과_종류의_원본_ID가_겹쳐도_분류와_기존_집계가_섞이지_않는다(conn, review_raw):
    from cholog_mcp.feedback import get_repeated_feedback
    from pipeline.tagger import tag_mission
    from pipeline.verify import measure_topic_prs

    reviews = json.loads((review_raw / "review/1.json").read_text())
    reviews[0]["body"] = "책임을 나누는 설계를 선택한 이유와 장단점을 함께 이야기해 주세요."
    (review_raw / "review/1.json").write_text(json.dumps(reviews))
    issues = json.loads((review_raw / "issue/1.json").read_text())
    issues[0]["user"] = {"login": "reviewer-id"}
    issues[0]["body"] = "네이밍을 바꿀 때 어떤 표현이 가장 명확한지 함께 이야기해 주세요."
    (review_raw / "issue/1.json").write_text(json.dumps(issues))
    another = Mission(id="another", repo="owner/other", name="다른 미션")
    for mission in (MISSION, another):
        load_mission(conn, mission, review_raw)
        tag_mission(conn, mission.id)
    before = {m.id: get_repeated_feedback(conn, m.id) for m in (MISSION, another)}
    other_rows = conn.execute("SELECT * FROM comments WHERE mission_id='another' ORDER BY id").fetchall()
    other_tags = conn.execute(
        "SELECT ct.* FROM comment_topics ct JOIN comments c ON c.id=ct.comment_id "
        "WHERE c.mission_id='another' ORDER BY comment_id,topic_id"
    ).fetchall()
    assert other_tags

    for _ in range(2):
        load_mission(conn, MISSION, review_raw)
        tag_mission(conn, MISSION.id)

    assert conn.execute("SELECT * FROM comments WHERE mission_id='another' ORDER BY id").fetchall() == other_rows
    assert conn.execute(
        "SELECT ct.* FROM comment_topics ct JOIN comments c ON c.id=ct.comment_id "
        "WHERE c.mission_id='another' ORDER BY comment_id,topic_id"
    ).fetchall() == other_tags
    for mission in (MISSION, another):
        assert get_repeated_feedback(conn, mission.id) == before[mission.id]
        assert measure_topic_prs(conn, mission.id)["responsibility"] == 1
        tags = set(conn.execute(
            "SELECT c.kind,ct.topic_id FROM comments c JOIN comment_topics ct ON c.id=ct.comment_id "
            "WHERE c.mission_id=? AND c.github_id=10", (mission.id,),
        ))
        assert ("review", "responsibility") in tags and ("issue", "naming") in tags
        assert ("issue", "responsibility") not in tags and ("review", "naming") not in tags


def test_같은_원본_재적재로_내부_키가_바뀌어도_커서를_이어_읽는다(conn, review_raw):
    from cholog_mcp.review_context import get_review_context

    reviews = json.loads((review_raw / "review/1.json").read_text())
    reviews.extend(_comment(1000 + n, "reviewer-id", "후속 답변", in_reply_to_id=10) for n in range(51))
    (review_raw / "review/1.json").write_text(json.dumps(reviews))
    load_mission(conn, MISSION, review_raw)
    first = get_review_context(conn, MISSION.id, ["learner-01"])
    cursor = first["pagination"]["next_cursor"]
    assert cursor is not None
    before = get_review_context(conn, MISSION.id, ["learner-01"], cursor=cursor)
    old_keys = conn.execute("SELECT id FROM comments WHERE mission_id=? ORDER BY id", (MISSION.id,)).fetchall()
    # 다른 미션이 원본 ID와 겹치는 내부 키를 점유하게 한다.
    load_mission(conn, Mission(id="another", repo="owner/other", name="다른 미션"), review_raw)
    load_mission(conn, MISSION, review_raw)
    assert conn.execute("SELECT id FROM comments WHERE mission_id=? ORDER BY id", (MISSION.id,)).fetchall() != old_keys
    assert get_review_context(conn, MISSION.id, ["learner-01"], cursor=cursor) == before


@pytest.fixture
def schema_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def test_최신_스키마는_내부_키와_원본_ID를_분리하고_종류별_중복을_막는다(schema_conn):
    create_schema(schema_conn)
    schema_conn.execute("INSERT INTO missions VALUES ('test-mission','owner/repo','미션',NULL)")
    sql = (
        "INSERT INTO comments (github_id,mission_id,pr_number,kind,is_pr_author,body,created_at,updated_at,url) "
        "VALUES (10,'test-mission',?,?,0,'본문','2026-03-01','2026-03-01','url')"
    )
    schema_conn.execute(sql, (1, "review"))
    schema_conn.execute(sql, (1, "issue"))
    rows = schema_conn.execute("SELECT id,github_id,in_reply_to_id FROM comments ORDER BY id").fetchall()
    assert rows == [(1, 10, None), (2, 10, None)]
    with pytest.raises(sqlite3.IntegrityError):
        schema_conn.execute(sql, (2, "review"))
    schema_conn.execute("INSERT INTO topics VALUES ('topic',NULL,NULL,'주제')")
    schema_conn.execute("INSERT INTO comment_topics VALUES (1,'topic','keyword',1)")
    with pytest.raises(sqlite3.IntegrityError):
        schema_conn.execute("INSERT INTO comment_topics VALUES (10,'topic','keyword',1)")
    assert schema_conn.execute(
        "SELECT c.kind,c.github_id FROM comment_topics ct JOIN comments c ON c.id=ct.comment_id"
    ).fetchall() == [("review", 10)]


def test_구_스키마는_변경_없이_새_DB_생성을_안내한다(schema_conn):
    schema_conn.execute("CREATE TABLE comments (id INTEGER PRIMARY KEY)")
    with pytest.raises(ValueError, match="최신 스키마로 새 DB"):
        create_schema(schema_conn)
    assert [r[1] for r in schema_conn.execute("PRAGMA table_info(comments)")] == ["id"]
    assert schema_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("comments",)]


@pytest.mark.parametrize("definition,index_sql", [
    ("INTEGER", ""),
    ("INTEGER", "CREATE UNIQUE INDEX wrong_identity ON comments(mission_id,kind,github_id)"),
    ("INTEGER NOT NULL", ""),
    ("INTEGER NOT NULL", "CREATE UNIQUE INDEX wrong_identity ON comments(mission_id,kind,github_id) WHERE kind='review'"),
    ("INTEGER NOT NULL", "CREATE UNIQUE INDEX wrong_identity ON comments(mission_id,pr_number,kind,github_id)"),
])
def test_식별자_제약이_다른_DB는_새로_생성하도록_안내한다(schema_conn, definition, index_sql):
    sql = SCHEMA.replace("github_id    INTEGER NOT NULL", f"github_id    {definition}")
    sql = sql.replace(",\n    UNIQUE (mission_id, kind, github_id)", "")
    schema_conn.executescript(sql)
    if index_sql:
        schema_conn.execute(index_sql)
    before = schema_conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
    with pytest.raises(ValueError, match="최신 스키마로 새 DB"):
        create_schema(schema_conn)
    assert schema_conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall() == before


@pytest.mark.parametrize("primary_key,suffix", [("INTEGER PRIMARY KEY DESC", ""), ("INTEGER PRIMARY KEY", "WITHOUT ROWID")])
def test_내부_키가_자동_부여되지_않는_DB는_거절한다(schema_conn, primary_key, suffix):
    sql = SCHEMA.replace("id           INTEGER PRIMARY KEY", f"id           {primary_key}")
    sql = sql.replace("UNIQUE (mission_id, kind, github_id)\n);", f"UNIQUE (mission_id, kind, github_id)\n) {suffix};")
    schema_conn.executescript(sql)
    with pytest.raises(ValueError, match="최신 스키마로 새 DB"):
        create_schema(schema_conn)
