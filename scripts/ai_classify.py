"""미션의 리뷰어 코멘트를 claude -p로 개념 분류하고, 결과를 고정본으로 저장한다.

    uv run python -m scripts.ai_classify run java-calculator --limit 3   # 묶음마다 저장. 끊기면 다시 실행해 이어서 돌린다
    uv run python -m scripts.ai_classify save java-calculator            # 묶음을 모아 pipeline/ai_topics/<mission>.json으로 고정

입력은 코멘트 id(GitHub ID), 파일 경로(path), 원문(body)뿐이다. 묶음 결과는 data/ai/<mission>/batches/에 둔다 (git 밖).
비용은 scripts/ai_budget.py의 규칙을 따른다.
"""

import argparse
import json
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from pipeline.ai_store import AiTopics, save_ai_topics
from pipeline.topics import CONCEPTS, CONCEPTS_VERSION, Concept
from scripts.ai_budget import Budget, BudgetReached, call_claude

BATCH = 20
TRIES = 2  # 실패한 묶음은 한 번만 다시 보낸다
WORKERS = 5
MODEL = "opus"
DB = Path("data/cholog.db")
OUT = Path("data/ai")

# 프롬프트를 바꾸면 PROMPT_VERSION을 고친다. 고정본의 prompt_version에 적힌다.
# - 2026-11-12: AI 분류 시험과 같은 프롬프트. 개념은 id와 이름만 준다 (v1)
# - v2-설명: 개념마다 기준·예시·이웃 개념과의 차이(topics.Description)를 더 준다
PROMPT_V1 = "2026-11-12"
PROMPT_V2 = "v2-설명"
PROMPT_VERSION = PROMPT_V2

SYSTEM_PROMPT = """너는 Java 미션 PR에 리뷰어가 남긴 코드 리뷰 코멘트를 주제로 분류한다.
각 코멘트에 아래 개념 목록에서 해당하는 개념 id를 붙인다.

규칙
- 여러 개면 모두 적는다. 주제가 없으면 빈 배열.
- 칭찬만 있으면 개념 이름이 나와도 빈 배열. "많이 지적받는 게 뭐야"에 답하려는 분류이므로 지적만 센다.
- 목록에 맞는 개념이 없으면 빈 배열. 목록에 없는 id는 만들지 않는다.

개념 목록 ({concepts_header})
{concepts}

출력
- JSON 객체 하나만 출력한다. 형식: {{"코멘트 id": ["개념 id", ...]}}
- 입력한 모든 코멘트 id를 키로 넣는다.
- 설명, 코드 블록 표시 없이 JSON만 출력한다."""

USER_PROMPT = """아래 코멘트 {count}개를 분류해 줘. 각 항목은 코멘트 id, 파일 경로(path), 원문(body)이다.

{comments}"""


def concept_lines(concept: Concept, version: str) -> str:
    line = f"- {concept.id}: {concept.name}"
    if version == PROMPT_V1 or concept.description is None:
        return line
    description = concept.description
    return "\n".join([
        line,
        f"  기준: {description.definition}",
        f"  예: {description.example}",
        f"  헷갈리는 개념: {description.contrast}",
    ])


def system_prompt(version: str = PROMPT_VERSION) -> str:
    if version not in (PROMPT_V1, PROMPT_V2):
        raise ValueError(f"모르는 프롬프트 버전: {version}")
    header = "id: 이름" if version == PROMPT_V1 else "id: 이름, 아래 줄에 기준·예시·헷갈리는 개념과의 차이"
    concepts = "\n".join(concept_lines(concept, version) for concept in CONCEPTS)
    return SYSTEM_PROMPT.format(concepts_header=header, concepts=concepts)


def parse(text: str) -> dict:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def reviewer_comments(mission_id: str, db: Path = DB) -> list[dict]:
    """리뷰어 코멘트를 (kind, GitHub ID) 순으로. 묶음이 실행마다 같아야 이어서 돌릴 수 있다."""
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)")}
    github_id = "github_id" if "github_id" in columns else "id"
    rows = conn.execute(
        f"SELECT kind, {github_id}, pr_number, path, body FROM comments "
        "WHERE mission_id = ? AND is_pr_author = 0 ORDER BY 1, 2",
        (mission_id,),
    ).fetchall()
    conn.close()
    return [{"kind": kind, "github_id": gid, "pr": pr, "path": path, "body": body}
            for kind, gid, pr, path, body in rows]


def batch_dir(mission_id: str) -> Path:
    return OUT / mission_id / "batches"


def classify_batch(budget: Budget, label: str, system: str, batch: list[dict]) -> tuple[dict, list[str]]:
    items = [{"id": c["github_id"], "path": c["path"], "body": c["body"]} for c in batch]
    user = USER_PROMPT.format(count=len(items), comments=json.dumps(items, ensure_ascii=False, indent=1))
    expected = {str(c["github_id"]) for c in batch}
    last = None
    for attempt in range(TRIES):
        try:
            result = call_claude(budget, f"{label} try{attempt + 1}", MODEL, system, user)
            labels = parse(result.get("result", ""))
            if not isinstance(labels, dict) or not expected <= set(map(str, labels)):
                raise ValueError("빠진 id 또는 형식 오류")
            models = list((result.get("modelUsage") or {}).keys())
            return {key: labels[key] for key in expected}, models
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            last = error
    raise RuntimeError(f"{TRIES}번 시도해도 실패: {last}")


def cmd_run(args) -> None:
    concept_ids = {c.id for c in CONCEPTS}
    system = system_prompt()
    comments = reviewer_comments(args.mission)
    batches = [comments[i:i + BATCH] for i in range(0, len(comments), BATCH)]
    out = batch_dir(args.mission)
    out.mkdir(parents=True, exist_ok=True)
    todo = [n for n in range(len(batches)) if not (out / f"{n:04d}.json").exists()]
    print(f"{args.mission}: 코멘트 {len(comments)}개, 묶음 {len(batches)}개, 남은 묶음 {len(todo)}개", flush=True)
    budget = Budget(f"classify:{args.mission}", args.limit)
    started = time.time()
    failed, stopped = [], []

    def work(n: int) -> None:
        batch = batches[n]
        try:
            labels, models = classify_batch(budget, f"{args.mission} #{n}", system, batch)
        except BudgetReached as reached:
            stopped.append(n)
            print(f"멈춤 (비용 상한) #{n}: {reached}", flush=True)
            return
        except RuntimeError as error:
            failed.append({"batch": n, "error": str(error)})
            print(f"실패 #{n}: {error}", flush=True)
            return
        records = []
        for comment in batch:
            topics = labels[str(comment["github_id"])]
            topics = topics if isinstance(topics, list) else []
            records.append({"kind": comment["kind"], "github_id": comment["github_id"],
                            "topics": sorted({t for t in topics if t in concept_ids}),
                            "invalid": [t for t in topics if t not in concept_ids]})
        (out / f"{n:04d}.json").write_text(json.dumps({"models": models, "comments": records}, ensure_ascii=False))
        print(f"#{n} 저장 ({time.time() - started:.0f}s, 누적 {budget.total:.3f}달러)", flush=True)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(work, todo))
    (OUT / args.mission / "run-status.json").write_text(json.dumps({
        "wall_seconds": round(time.time() - started, 1), "total_usd": budget.total,
        "failed": failed, "stopped_by_budget": sorted(stopped)}, ensure_ascii=False, indent=1))
    print(f"끝: {time.time() - started:.0f}s, 누적 {budget.total:.3f}달러, 실패 {len(failed)}, 상한으로 멈춤 {len(stopped)}")


def cmd_save(args) -> None:
    comments = reviewer_comments(args.mission)
    expected_batches = (len(comments) + BATCH - 1) // BATCH
    files = sorted(batch_dir(args.mission).glob("*.json"))
    topics, models, invalid = {}, set(), []
    for path in files:
        data = json.loads(path.read_text())
        models.update(data["models"])
        for record in data["comments"]:
            topics[(record["kind"], record["github_id"])] = record["topics"]
            invalid.extend(record["invalid"])
    print(f"묶음 {len(files)}/{expected_batches}개, 코멘트 {len(topics)}/{len(comments)}개, 버린 id {len(invalid)}개")
    path = save_ai_topics(AiTopics(
        mission_id=args.mission,
        classified_at=args.date or date.today().isoformat(),
        model=",".join(sorted(m for m in models if MODEL in m)) or MODEL,
        prompt_version=PROMPT_VERSION,
        concepts_version=CONCEPTS_VERSION,
        topics=topics,
    ))
    print(f"저장: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("mission")
    p.add_argument("--limit", type=float, required=True, help="이 미션 분류의 누적 비용 상한(달러)")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("save")
    p.add_argument("mission")
    p.add_argument("--date", help="분류 날짜 (기본: 오늘)")
    p.set_defaults(func=cmd_save)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
