"""수집한 원본 JSON을 SQLite에 넣는다.

원본 위치: data/raw/<mission>/prs.json, review/<PR 번호>.json, issue/<PR 번호>.json
(pipeline.fetch가 만드는 구조)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from cholog_mcp.missions import Mission

KINDS = ("review", "issue")


def read_json_arrays(path: Path) -> list[dict]:
    """`gh api --paginate`는 페이지마다 배열을 이어 붙여 쓴다 ([..][..]). 하나로 합쳐 읽는다."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    decoder = json.JSONDecoder()
    items: list[dict] = []
    position = 0
    while position < len(text):
        parsed, position = decoder.raw_decode(text, position)
        items.extend(parsed if isinstance(parsed, list) else [parsed])
        while position < len(text) and text[position].isspace():
            position += 1
    return [item for item in items if isinstance(item, dict) and "body" in item]


def read_synced_at(raw_dir: Path) -> str:
    """수집 시각. meta.json이 없으면 prs.json을 마지막으로 고친 시각을 쓴다."""
    meta_path = raw_dir / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))["fetched_at"]
    modified = datetime.fromtimestamp((raw_dir / "prs.json").stat().st_mtime)
    return modified.astimezone().isoformat(timespec="seconds")


def load_mission(conn: sqlite3.Connection, mission: Mission, raw_dir: Path) -> dict[str, int]:
    """미션의 PR과 코멘트를 원본으로 통째로 바꿔 넣는다. 넣은 수를 돌려준다."""
    prs = json.loads((raw_dir / "prs.json").read_text(encoding="utf-8"))
    pr_rows = []
    comment_rows = []
    for pr in prs:
        number = pr["number"]
        pr_author = (pr.get("author") or {}).get("login")
        pr_rows.append((
            mission.id,
            number,
            pr_author,
            pr["title"],
            pr["createdAt"],
            f"https://github.com/{mission.repo}/pull/{number}",
        ))
        for kind in KINDS:
            for comment in read_json_arrays(raw_dir / kind / f"{number}.json"):
                author = (comment.get("user") or {}).get("login")
                comment_rows.append((
                    comment["id"],
                    mission.id,
                    number,
                    kind,
                    author,
                    int(author is not None and pr_author is not None and author.lower() == pr_author.lower()),
                    comment.get("body") or "",
                    comment.get("path"),
                    comment.get("diff_hunk"),
                    comment["created_at"],
                    comment["updated_at"],
                    comment["html_url"],
                    comment.get("in_reply_to_id") if kind == "review" else None,
                ))

    # 기존 집계 도구가 score 동률에서 c.id로 정렬한다. 원본 ID 순서를 보존한다.
    comment_rows.sort(key=lambda row: (row[0], row[3]))
    with conn:
        conn.execute(
            "DELETE FROM comment_topics WHERE comment_id IN (SELECT id FROM comments WHERE mission_id = ?)",
            (mission.id,),
        )
        conn.execute("DELETE FROM comments WHERE mission_id = ?", (mission.id,))
        conn.execute("DELETE FROM pull_requests WHERE mission_id = ?", (mission.id,))
        conn.execute(
            "INSERT INTO missions (id, repo, name, synced_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET repo = excluded.repo, name = excluded.name, "
            "synced_at = excluded.synced_at",
            (mission.id, mission.repo, mission.name, read_synced_at(raw_dir)),
        )
        conn.executemany("INSERT INTO pull_requests VALUES (?, ?, ?, ?, ?, ?)", pr_rows)
        try:
            conn.executemany(
                "INSERT INTO comments (github_id, mission_id, pr_number, kind, author, is_pr_author, "
                "body, path, diff_hunk, created_at, updated_at, url, in_reply_to_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", comment_rows,
            )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"코멘트 식별자 중복 또는 필수값 오류: {error}") from error

    return {"pull_requests": len(pr_rows), "comments": len(comment_rows)}
