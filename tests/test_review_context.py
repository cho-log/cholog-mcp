import base64
import json
import sqlite3
from datetime import date

import pytest

from cholog_mcp.review_context import get_review_context

MISSION = "java-racingcar"


def ask(conn, authors=None, **kwargs):
    return get_review_context(conn, MISSION, ["learner-01"] if authors is None else authors, **kwargs)


def conversations(result):
    return [c for pr in result["pull_requests"] for c in pr["conversations"]]


def comments(result):
    return [c for conversation in conversations(result) for c in conversation["comments"]]


def add_comment(conn, id, parent=None, body="본문", kind="review", created="2026-03-01T00:00:00Z", diff=None):
    conn.execute(
        "INSERT INTO comments (github_id, mission_id, pr_number, kind, author, is_pr_author, "
        "body, path, diff_hunk, created_at, updated_at, url, in_reply_to_id) "
        "VALUES (?, ?, 1, ?, 'reviewer-id', 0, ?, NULL, ?, ?, ?, ?, ?)",
        (id, MISSION, kind, body, diff, created, created, f"https://example.com/{kind}/{id}", parent),
    )


def clear_comments(conn):
    conn.execute("DELETE FROM comments")


def all_pages(conn, **kwargs):
    results = []
    cursor = None
    while True:
        result = ask(conn, cursor=cursor, **kwargs)
        results.append(result)
        if not result["pagination"]["has_more"]:
            assert result["pagination"]["next_cursor"] is None
            return results
        cursor = result["pagination"]["next_cursor"]
        assert len(results) < 100


def test_질문과_후속_답변_원문과_근거를_보존한다(review_conn):
    result = ask(review_conn)
    thread = next(c for c in conversations(result) if c["id"] == "review:10")
    assert [c["id"] for c in thread["comments"]] == [10, 11, 12]
    assert [c["is_pr_author"] for c in thread["comments"]] == [False, True, False]
    assert [c["parent_status"] for c in thread["comments"]] == ["none", "found", "found"]
    assert thread["comments"][2]["in_reply_to_id"] == 11
    c = thread["comments"][0]
    original = review_conn.execute(
        "SELECT body, url, path, diff_hunk, created_at, updated_at FROM comments WHERE kind='review' AND github_id=10"
    ).fetchone()
    assert tuple(c[k] for k in ("body", "url", "path", "diff_hunk", "created_at", "updated_at")) == original
    assert c["body"].startswith(">") and len(c["body"]) > 300
    assert thread["partial"] is False and thread["total_comments"] == 3
    assert result["scope"]["data_as_of"] == "2026-03-03T09:00:00+09:00"
    pr = result["pull_requests"][0]
    assert (pr["number"], pr["title"], pr["author"]) == (1, "제출 1", "Learner-01")
    assert pr["url"].endswith("/pull/1")
    assert any("최신" in note for note in result["limitations"]["notes"])


def test_태그_테이블이_없어도_모든_댓글을_조회한다(review_conn):
    review_conn.execute("DROP TABLE comment_topics")
    review_conn.execute("DROP TABLE topics")
    assert len(comments(ask(review_conn))) == 8


def test_작성자_미션_날짜_필터와_없는_작성자_및_빈_PR(review_conn):
    review_conn.execute("INSERT INTO missions VALUES ('another', 'owner/other', '다른 미션', NULL)")
    review_conn.execute("INSERT INTO pull_requests VALUES ('another', 1, 'learner-01', '혼입 금지', '2026-03-01', 'other')")
    review_conn.execute(
        "INSERT INTO comments (github_id,mission_id,pr_number,kind,is_pr_author,body,created_at,updated_at,url) "
        "VALUES (10,'another',1,'review',0,'혼입 금지','2026-03-01','2026-03-01','other')"
    )
    result = ask(review_conn, authors=[" @LEARNER-01 ", "learner-02", "learner-01", "missing-id"], since=date(2026, 3, 1))
    assert result["scope"]["authors"] == ["learner-01", "learner-02", "missing-id"]
    assert result["scope"]["pr_numbers"] == [1, 3]
    assert result["scope"]["authors_not_found"] == ["learner-02", "missing-id"]
    assert result["pull_requests"][1]["conversations"] == []
    assert all(c["body"] != "혼입 금지" for c in comments(result))
    assert ask(review_conn, ["missing-id"])["pull_requests"] == []


def test_날짜는_UTC_경계와_PR_생성일에_적용한다(review_conn):
    review_conn.execute("UPDATE pull_requests SET created_at='2026-03-01T09:00:00+09:00' WHERE number=1")
    review_conn.execute("UPDATE comments SET created_at='2025-01-01' WHERE github_id=10")
    assert len(comments(ask(review_conn, since=date(2026, 3, 1)))) == 8
    review_conn.execute("UPDATE pull_requests SET created_at='2026-03-01T08:59:59+09:00' WHERE number=1")
    assert ask(review_conn, since=date(2026, 3, 1))["scope"]["pr_numbers"] == [3]


def test_다른_PR과_issue는_부모로_연결하지_않는다(review_conn):
    result = ask(review_conn, ["learner-01", "learner-02"])
    prs = {pr["number"]: pr for pr in result["pull_requests"]}
    threads = {c["id"]: c for c in prs[1]["conversations"]}
    assert [c["id"] for c in threads["review:13"]["comments"]] == [13, 14]
    assert threads["review:13"]["comments"][0]["parent_status"] == "missing"
    assert threads["review:15"]["comments"][0]["parent_status"] == "missing"
    assert result["limitations"]["missing_parent_count"] == 2
    issue = threads["issue"]["comments"]
    assert [c["id"] for c in issue] == [10, 20]
    assert all(c["in_reply_to_id"] is None and c["parent_status"] == "not_applicable" for c in issue)


def test_다른_미션의_부모_ID를_찾아_연결하지_않는다(review_conn):
    review_conn.execute("INSERT INTO missions VALUES ('another','owner/other','다른 미션',NULL)")
    review_conn.execute(
        "INSERT INTO comments (github_id,mission_id,pr_number,kind,is_pr_author,body,created_at,updated_at,url) "
        "VALUES (999,'another',1,'review',0,'다른 저장소 부모','2026-03-01','2026-03-01','other')"
    )
    result = ask(review_conn)
    assert next(c for c in comments(result) if c["id"] == 13)["parent_status"] == "missing"
    assert all(c["body"] != "다른 저장소 부모" for c in comments(result))


@pytest.mark.parametrize("authors", [[], [""], ["@"], ["two ids"], ["a,b"], ["-bad"], ["bad--id"], ["x" * 40], ["a"] * 101])
def test_잘못된_작성자는_오류다(review_conn, authors):
    with pytest.raises(ValueError, match="authors|GitHub"):
        ask(review_conn, authors)


def test_데이터가_없는_미션은_빈_결과와_구분한다(review_conn):
    with pytest.raises(ValueError, match="데이터가 없는 미션"):
        get_review_context(review_conn, "missing", ["learner-01"])


def test_순환_데이터는_멈추지_않고_한계를_표시한다(review_conn):
    clear_comments(review_conn)
    add_comment(review_conn, 1, 2)
    add_comment(review_conn, 2, 1)
    result = ask(review_conn)
    assert len(comments(result)) == 2
    assert result["limitations"]["cycle_comment_count"] == 2
    assert all(c["parent_status"] == "cycle" for c in comments(result))


def test_50댓글_경계는_대화를_온전히_유지한다(review_conn):
    clear_comments(review_conn)
    for i in range(50):
        add_comment(review_conn, i + 1, 1 if i else None)
    result = ask(review_conn)
    assert len(comments(result)) == 50
    assert conversations(result)[0]["partial"] is False


def test_남은_공간이_부족하면_작은_대화는_통째로_다음_페이지다(review_conn):
    clear_comments(review_conn)
    for root in (1, 101):
        for i in range(30):
            add_comment(review_conn, root + i, root if i else None)
    pages = all_pages(review_conn)
    assert [len(comments(p)) for p in pages] == [30, 30]
    assert all(not c["partial"] for p in pages for c in conversations(p))


def test_큰_대화는_이어_읽으면_누락과_중복이_없다(review_conn):
    clear_comments(review_conn)
    for i in range(123):
        add_comment(review_conn, i + 1, 1 if i else None)
    pages = all_pages(review_conn)
    assert [len(comments(p)) for p in pages] == [50, 50, 23]
    assert [c["id"] for p in pages for c in comments(p)] == list(range(1, 124))
    chunks = [conversations(p)[0] for p in pages]
    assert [(c["start_offset"], c["end_offset"], c["has_more"]) for c in chunks] == [(0, 50, True), (50, 100, True), (100, 123, False)]
    assert all(c["partial"] and c["total_comments"] == 123 for c in chunks)
    assert "cursor" in pages[0]["pagination"]["note"]
    assert ask(review_conn) == pages[0]


def test_본문과_diff_문자_예산과_단일_큰_댓글(review_conn):
    clear_comments(review_conn)
    add_comment(review_conn, 1, body="가" * 12000, diff="x" * 12000)
    add_comment(review_conn, 2, 1)
    assert [len(comments(p)) for p in all_pages(review_conn)] == [1, 1]
    review_conn.execute("UPDATE comments SET body=? WHERE github_id=1", ("나" * 24001,))
    pages = all_pages(review_conn)
    assert pages[0]["pagination"]["oversized_comment"] is True
    assert comments(pages[0])[0]["body"] == "나" * 24001


def test_대화_개수_경계와_생성_시각_동률_정렬(review_conn):
    clear_comments(review_conn)
    for id in reversed(range(1, 22)):
        add_comment(review_conn, id)
    pages = all_pages(review_conn)
    assert [len(conversations(p)) for p in pages] == [20, 1]
    assert [c["id"] for p in pages for c in comments(p)] == list(range(1, 22))


def test_비어있는_PR도_20개씩_누락과_중복_없이_읽는다(review_conn):
    clear_comments(review_conn)
    review_conn.execute("DELETE FROM pull_requests")
    review_conn.executemany(
        "INSERT INTO pull_requests VALUES (?,?,'learner-01','빈 PR','2026-03-01',?)",
        [(MISSION, n, f"pr-{n}") for n in range(1, 42)],
    )
    pages = all_pages(review_conn)
    assert [len(p["pull_requests"]) for p in pages] == [20, 20, 1]
    assert [pr["number"] for p in pages for pr in p["pull_requests"]] == list(range(1, 42))


def test_생성_시각은_UTC로_정렬하고_값을_그대로_돌려준다(review_conn):
    clear_comments(review_conn)
    add_comment(review_conn, 1, created="2026-03-01T09:00:00+09:00")
    add_comment(review_conn, 2, 1, created="2026-03-01T00:00:01Z")
    result = ask(review_conn)
    assert [c["id"] for c in comments(result)] == [1, 2]
    assert comments(result)[0]["created_at"] == "2026-03-01T09:00:00+09:00"


@pytest.mark.parametrize("cursor", ["", "!not-base64", "e30=", "x" * 2049])
def test_깨진_커서는_오류다(review_conn, cursor):
    with pytest.raises(ValueError, match="커서"):
        ask(review_conn, cursor=cursor)


def test_커서_위치_버전_범위와_DB_변경을_검증한다(review_conn):
    clear_comments(review_conn)
    for i in range(51):
        add_comment(review_conn, i + 1, 1 if i else None)
    cursor = ask(review_conn)["pagination"]["next_cursor"]
    payload = json.loads(base64.urlsafe_b64decode(cursor))
    for change in ({"page": -1}, {"page": 100}, {"page": True}, {"version": 99}):
        altered = base64.urlsafe_b64encode(json.dumps(payload | change).encode()).decode()
        with pytest.raises(ValueError, match="커서"):
            ask(review_conn, cursor=altered)
    with pytest.raises(ValueError, match="커서"):
        ask(review_conn, authors=["learner-02"], cursor=cursor)
    with pytest.raises(ValueError, match="커서"):
        ask(review_conn, since=date(2026, 1, 1), cursor=cursor)
    # 기준 시각이 같더라도 원문 수정으로 무효화된다.
    review_conn.execute("UPDATE comments SET body='수정' WHERE github_id=1")
    with pytest.raises(ValueError, match="커서"):
        ask(review_conn, cursor=cursor)


@pytest.mark.parametrize("sql", [
    "UPDATE missions SET synced_at='2026-04-01'",
    "UPDATE pull_requests SET title='변경' WHERE number=1",
    "DELETE FROM comments WHERE github_id=2",
])
def test_수집_시각_PR_수정_삭제에도_커서를_거절한다(review_conn, sql):
    clear_comments(review_conn)
    for i in range(51):
        add_comment(review_conn, i + 1, 1 if i else None)
    cursor = ask(review_conn)["pagination"]["next_cursor"]
    review_conn.execute(sql)
    with pytest.raises(ValueError, match="커서"):
        ask(review_conn, cursor=cursor)


def test_수집_기준_시각이_없으면_한계를_알린다(review_conn):
    review_conn.execute("UPDATE missions SET synced_at=NULL")
    result = ask(review_conn)
    assert result["scope"]["data_as_of"] is None
    assert any("시각이 저장되어 있지 않다" in note for note in result["limitations"]["notes"])


def test_조회_중_DB가_갱신되어도_한_응답은_같은_스냅샷이다(review_conn, context_db_file):
    review_conn.execute("PRAGMA journal_mode=WAL")
    changed = []

    def update_between_reads(sql):
        if sql.startswith("SELECT p.number") and not changed:
            changed.append(True)
            writer = sqlite3.connect(context_db_file)
            try:
                writer.execute("UPDATE pull_requests SET title='새 제목' WHERE number=1")
                writer.execute("UPDATE comments SET body='새 본문' WHERE kind='review' AND github_id=10")
                writer.commit()
            finally:
                writer.close()

    review_conn.set_trace_callback(update_between_reads)
    try:
        result = ask(review_conn)
    finally:
        review_conn.set_trace_callback(None)
    assert changed
    assert result["pull_requests"][0]["title"] == "제출 1"
    assert next(c for c in comments(result) if c["kind"] == "review" and c["id"] == 10)["body"].startswith(">")
    assert not review_conn.in_transaction
    assert ask(review_conn)["pull_requests"][0]["title"] == "새 제목"
