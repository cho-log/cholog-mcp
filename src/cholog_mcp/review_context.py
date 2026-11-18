"""저장된 리뷰 대화를 돌려준다. MCP·분류기·실행 방식에 의존하지 않는다."""

import base64
import binascii
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone

from cholog_mcp.db import SCHEMA_ERROR, has_comment_identity_constraints

PAGE_COMMENTS = 50
PAGE_TEXT_CHARS = 24_000
PAGE_ITEMS = 20
CURSOR_VERSION = 1

_LOGIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?")
CURSOR_ERROR = "커서가 잘못되었거나 조회 범위·데이터가 바뀌었다. cursor를 비우고 처음부터 조회한다."

NOTES = [
    "사전 수집한 자료다. data_as_of 이후의 변경과 호출 시점의 최신 GitHub 상태를 보장하지 않는다.",
    "삭제·부분 수집·수집 누락의 정확한 범위는 알 수 없다. 부모 ID가 NULL이면 최상위인지 부모 정보 미수집인지 구분할 수 없다.",
    "diff_hunk는 리뷰 당시 일부 코드이며 현재 전체 구현의 근거가 아니다. PR 본문과 리뷰 제출 총평은 수집하지 않는다.",
]


def get_review_context(
    conn: sqlite3.Connection,
    mission: str,
    authors: list[str],
    since: date | None = None,
    cursor: str | None = None,
) -> dict:
    """선택한 작성자의 PR·댓글을 같은 읽기 스냅샷에서 조회한다. 계약은 tool-spec.md 6번."""
    requested = _normalize_authors(authors)
    if since is not None and (not isinstance(since, date) or isinstance(since, datetime)):
        raise ValueError("since는 YYYY-MM-DD 날짜여야 한다.")
    # 외부 트랜잭션이 있으면 그대로 사용하고, 없으면 읽기 트랜잭션만 연다.
    started = not conn.in_transaction
    if started:
        conn.execute("BEGIN")
    try:
        return _read_context(conn, mission, requested, since, cursor)
    finally:
        if started:
            conn.rollback()


def _normalize_authors(authors: list[str]) -> list[str]:
    if not isinstance(authors, list) or not 1 <= len(authors) <= 100:
        raise ValueError("authors는 GitHub ID 1~100개의 목록이어야 한다.")
    normalized = set()
    for author in authors:
        if not isinstance(author, str):
            raise ValueError("authors의 각 값은 GitHub ID 문자열이어야 한다.")
        login = author.strip().removeprefix("@").lower()
        if not _LOGIN.fullmatch(login) or "--" in login:
            raise ValueError("authors의 각 값은 유효한 GitHub ID 하나여야 한다 (영숫자·하이픈, 1~39자).")
        normalized.add(login)
    return sorted(normalized)


def _read_context(conn, mission, requested, since, cursor):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)")}
    if columns and not has_comment_identity_constraints(conn):
        raise ValueError(SCHEMA_ERROR)
    synced = conn.execute("SELECT synced_at, repo FROM missions WHERE id=?", (mission,)).fetchone()
    if synced is None:
        raise ValueError(f"데이터가 없는 미션이다: {mission}")
    where = f"p.mission_id=? AND LOWER(p.author) IN ({','.join('?' for _ in requested)})"
    params = [mission, *requested]
    if since is not None:
        where += " AND julianday(p.created_at) >= julianday(?)"
        params.append(since.isoformat())
    prs = [
        dict(zip(("number", "title", "author", "url", "created_at"), row))
        for row in conn.execute(
            f"SELECT p.number,p.title,p.author,p.url,p.created_at FROM pull_requests p WHERE {where} ORDER BY p.number",
            params,
        )
    ]
    by_pr = {pr["number"]: [] for pr in prs}
    fields = ("id", "author", "is_pr_author", "kind", "body", "url", "path", "diff_hunk", "created_at", "updated_at", "in_reply_to_id")
    for row in conn.execute(
        "SELECT c.pr_number,c.github_id,c.author,c.is_pr_author,c.kind,c.body,c.url,c.path,c.diff_hunk,"
        "c.created_at,c.updated_at,c.in_reply_to_id FROM comments c "
        "JOIN pull_requests p ON p.mission_id=c.mission_id AND p.number=c.pr_number "
        f"WHERE {where}", params,
    ):
        comment = dict(zip(fields, row[1:]))
        comment["is_pr_author"] = bool(comment["is_pr_author"])
        by_pr[row[0]].append(comment)
    found = {pr["author"].lower() for pr in prs}
    scope = {
        "mission": mission, "authors": requested, "since": since.isoformat() if since else None,
        "authors_not_found": [a for a in requested if a not in found],
        "pr_count": len(prs), "pr_numbers": [pr["number"] for pr in prs], "data_as_of": synced[0],
    }
    for pr in prs:
        pr["conversations"] = _conversations(by_pr[pr["number"]])
    all_comments = [c for pr in prs for t in pr["conversations"] for c in t["comments"]]
    limitations = {
        "missing_parent_count": sum(c["parent_status"] == "missing" for c in all_comments),
        "cycle_comment_count": sum(c["parent_status"] == "cycle" for c in all_comments),
        "notes": list(NOTES),
    }
    if synced[0] is None:
        limitations["notes"].append("수집 기준 시각이 저장되어 있지 않다.")
    # 내부 키와 태그는 제외한다. 재적재 후 같은 외부 자료라면 같은 페이지를 읽는다.
    digest = hashlib.sha256(_json([CURSOR_VERSION, PAGE_COMMENTS, PAGE_TEXT_CHARS, PAGE_ITEMS, synced[1], scope, prs])).hexdigest()
    pages = _pages(prs)
    page = _decode_cursor(cursor, digest, len(pages)) if cursor is not None else 0
    selected = pages[page]
    more = page + 1 < len(pages)
    return {
        "scope": scope, "pull_requests": selected, "limitations": limitations,
        "pagination": {
            "has_more": more,
            "next_cursor": _encode_cursor(digest, page + 1) if more else None,
            "oversized_comment": any(_text_size(c) > PAGE_TEXT_CHARS for pr in selected for t in pr["conversations"] for c in t["comments"]),
            "note": (
                "partial인 대화는 일부 댓글만 제공했다. start_offset/end_offset과 total_comments로 범위를 확인한다. "
                "pagination.has_more가 true이면 같은 mission·authors·since와 next_cursor를 cursor로 보내 이어 읽는다. "
                "이전 페이지의 부모 원문은 반복하지 않는다."
            ),
        },
    }


def _time_key(comment):
    try:
        timestamp = datetime.fromisoformat(comment["created_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("DB 댓글의 생성 시각이 잘못되었다. 원본과 재적재를 확인한다.") from error
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp, comment["id"]


def _conversations(comments):
    reviews = {c["id"]: c for c in comments if c["kind"] == "review"}
    parents = {comment_id: c["in_reply_to_id"] for comment_id, c in reviews.items() if c["in_reply_to_id"] in reviews}
    cycles = _cycle_ids(parents)
    # Union-find는 깊은 답글에서도 재귀 한계 없이 확인된 연결 요소를 묶는다.
    leaders = {comment_id: comment_id for comment_id in reviews}

    def root(comment_id):
        while leaders[comment_id] != comment_id:
            leaders[comment_id] = leaders[leaders[comment_id]]
            comment_id = leaders[comment_id]
        return comment_id

    for child, parent in parents.items():
        leaders[root(child)] = root(parent)
    groups = {}
    for comment_id, c in reviews.items():
        c["parent_status"] = (
            "cycle" if comment_id in cycles else "found" if comment_id in parents else
            "missing" if c["in_reply_to_id"] is not None else "none"
        )
        groups.setdefault(root(comment_id), []).append(c)
    conversations = []
    for group in groups.values():
        group.sort(key=_time_key)
        base = next((c for c in group if c["id"] not in parents), group[0])
        conversations.append({"id": f"review:{base['id']}", "kind": "review", "comments": group})
    issues = [c for c in comments if c["kind"] == "issue"]
    if issues:
        for c in issues:
            c["in_reply_to_id"] = None
            c["parent_status"] = "not_applicable"
        conversations.append({"id": "issue", "kind": "issue", "comments": sorted(issues, key=_time_key)})
    return sorted(conversations, key=lambda t: (*_time_key(t["comments"][0]), t["kind"]))


def _cycle_ids(parents):
    visited, cycles = set(), set()
    for start in parents:
        path, positions = [], {}
        current = start
        while current in parents and current not in visited:
            if current in positions:
                cycles.update(path[positions[current]:])
                break
            positions[current] = len(path)
            path.append(current)
            current = parents[current]
        visited.update(path)
    return cycles


def _text_size(comment):
    return len(comment["body"]) + len(comment["diff_hunk"] or "")


def _chunks(conversation):
    comments = conversation["comments"]
    offset = 0
    while offset < len(comments):
        end, size = offset, 0
        while end < len(comments) and end - offset < PAGE_COMMENTS:
            cost = _text_size(comments[end])
            if end > offset and size + cost > PAGE_TEXT_CHARS:
                break
            size += cost
            end += 1
        yield {
            **conversation, "comments": comments[offset:end], "total_comments": len(comments),
            "start_offset": offset, "end_offset": end,
            "partial": offset > 0 or end < len(comments), "has_more": end < len(comments),
        }
        offset = end


def _pages(prs):
    pages, page = [], []
    count, size, items = 0, 0, 0
    for pr in prs:
        chunks = (c for t in pr["conversations"] for c in _chunks(t)) if pr["conversations"] else (None,)
        for chunk in chunks:
            chunk_comments = chunk["comments"] if chunk else []
            chunk_size = sum(_text_size(c) for c in chunk_comments)
            if items and (items >= PAGE_ITEMS or count + len(chunk_comments) > PAGE_COMMENTS or size + chunk_size > PAGE_TEXT_CHARS):
                pages.append(page)
                page, count, size, items = [], 0, 0, 0
            if not page or page[-1]["number"] != pr["number"]:
                page.append({**pr, "conversations": []})
            if chunk:
                page[-1]["conversations"].append(chunk)
            count += len(chunk_comments)
            size += chunk_size
            items += 1
    if page or not pages:
        pages.append(page)
    return pages


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _encode_cursor(digest, page):
    return base64.urlsafe_b64encode(_json({"version": CURSOR_VERSION, "digest": digest, "page": page})).decode()


def _decode_cursor(cursor, digest, page_count):
    try:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048:
            raise ValueError
        value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if (not isinstance(value, dict) or set(value) != {"version", "digest", "page"}
                or type(value["version"]) is not int or value["version"] != CURSOR_VERSION
                or value["digest"] != digest or type(value["page"]) is not int
                or not 1 <= value["page"] < page_count):
            raise ValueError
        return value["page"]
    except (ValueError, TypeError, binascii.Error, UnicodeError, RecursionError) as error:
        raise ValueError(CURSOR_ERROR) from error
