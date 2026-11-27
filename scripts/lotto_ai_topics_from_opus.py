"""11/12 로또 opus 분류 결과를 AI 분류 고정본(pipeline/ai_topics/java-lotto.json)으로 옮긴다 (일회용).

    uv run python -m scripts.lotto_ai_topics_from_opus

원본은 data/ai/java-lotto-opus.json ({"GitHub ID": ["개념 id", ...]}, 리뷰어 코멘트 3,414개, git 밖)이다.
kind는 DB(data/cholog.db)의 comments에서 같은 GitHub ID로 찾는다. 주제 목록은 원본 그대로 옮긴다.
data/labels/ai/opus-v1-run1.json(같은 내용을 먼저 옮겨 둔 파일)이 있으면 원본과 다른 곳을 출력한다.
"""

import json
import sqlite3
import sys
from pathlib import Path

from pipeline.ai_store import AiTopics, Entry, save_ai_topics
from pipeline.topics import CONCEPTS

MISSION = "java-lotto"
SOURCE = Path("data/ai/java-lotto-opus.json")
EARLIER = Path("data/labels/ai/opus-v1-run1.json")
SYNCED_AT = "2026-11-05T14:07:26+09:00"  # 고정본을 만든 DB의 수집 시각 (missions.synced_at)
DB = Path("data/cholog.db")


def reviewer_kinds(db: Path) -> dict[int, str]:
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)")}
    github_id = "github_id" if "github_id" in columns else "id"
    rows = conn.execute(
        f"SELECT {github_id}, kind FROM comments WHERE mission_id = ? AND is_pr_author = 0", (MISSION,)).fetchall()
    conn.close()
    return dict(rows)


def main() -> None:
    source = {int(github_id): topics for github_id, topics in json.loads(SOURCE.read_text()).items()}
    kinds = reviewer_kinds(DB)
    no_kind = sorted(set(source) - set(kinds))
    not_in_source = sorted(set(kinds) - set(source))
    unknown = sorted({t for topics in source.values() for t in topics} - {c.id for c in CONCEPTS})
    print(f"원본 {len(source)}개, DB 리뷰어 코멘트 {len(kinds)}개, kind 못 찾음 {len(no_kind)}, "
          f"원본에 없는 DB 코멘트 {len(not_in_source)}, 사전에 없는 개념 id {unknown}")
    if no_kind or not_in_source or unknown:
        sys.exit("멈춤: 개수나 개념 id가 맞지 않는다")

    if EARLIER.exists():
        earlier = {int(key.split(":")[1]): (key.split(":")[0], topics)
                   for key, topics in json.loads(EARLIER.read_text())["topics"].items()}
        diffs = [gid for gid in set(source) | set(earlier)
                 if gid not in earlier or gid not in source
                 or sorted(earlier[gid][1]) != sorted(source[gid]) or earlier[gid][0] != kinds.get(gid)]
        print(f"{EARLIER}와 다른 코멘트 {len(diffs)}개" + (f": {sorted(diffs)[:20]}" if diffs else ""))

    path = save_ai_topics(AiTopics(
        mission_id=MISSION,
        model="claude-opus-5-5",
        entries={(kinds[gid], gid): Entry(list(topics), "2026-11-12", SYNCED_AT, "2026-11-12", "2026-11-12")
                 for gid, topics in source.items()},
    ))
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
