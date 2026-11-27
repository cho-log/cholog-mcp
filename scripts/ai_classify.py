"""미션의 리뷰어 코멘트를 claude -p로 개념 분류하고, 결과를 고정본으로 저장한다.

    uv run python -m scripts.ai_classify run java-calculator --limit 3      # 묶음마다 저장. 끊기면 다시 실행해 이어서 돌린다
    uv run python -m scripts.ai_classify save java-calculator               # 묶음을 모아 pipeline/ai_topics/<mission>.json으로 고정
    uv run python -m scripts.ai_classify update java-calculator --limit 1   # 고정본에 없거나 분류 뒤 고친 코멘트만 분류해 덧붙인다
    uv run python -m scripts.ai_classify update java-calculator --dry-run   # AI를 부르지 않고 대상 수와 예상 비용만 본다

입력은 코멘트 id(GitHub ID), 파일 경로(path), 원문(body)뿐이다. run의 묶음 결과는 data/ai/<mission>/batches/에 둔다 (git 밖).
update는 묶음마다 고정본에 바로 쓴다. 끊겨도 다시 실행하면 이미 분류한 코멘트는 대상에서 빠진다.
비용은 scripts/ai_budget.py의 규칙을 따른다.
"""

import argparse
import json
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pipeline.ai_store import AI_TOPICS_DIR, AiTopics, Entry, load_ai_topics, save_ai_topics
from pipeline.topics import CONCEPTS, CONCEPTS_VERSION
from scripts.ai_budget import COST_LOG, Budget, BudgetReached, call_claude

BATCH = 20
TRIES = 2  # 실패한 묶음은 한 번만 다시 보낸다
WORKERS = 5
MODEL = "opus"
DB = Path("data/cholog.db")
OUT = Path("data/ai")
USD_PER_COMMENT = 1.5 / 1000  # 실측: 로또 3,414개 5.38달러, 계산기 1,049개 1.50달러
# 분류 시각은 한국 시간으로 남긴다. 날짜만 있는 옛 항목도 한국 날짜다.
KST = timezone(timedelta(hours=9))

# 2026-11-12 AI 분류 시험과 같은 프롬프트. 바꾸면 PROMPT_VERSION을 고친다.
PROMPT_VERSION = "2026-11-12"

SYSTEM_PROMPT = """너는 Java 미션 PR에 리뷰어가 남긴 코드 리뷰 코멘트를 주제로 분류한다.
각 코멘트에 아래 개념 목록에서 해당하는 개념 id를 붙인다.

규칙
- 여러 개면 모두 적는다. 주제가 없으면 빈 배열.
- 칭찬만 있으면 개념 이름이 나와도 빈 배열. "많이 지적받는 게 뭐야"에 답하려는 분류이므로 지적만 센다.
- 목록에 맞는 개념이 없으면 빈 배열. 목록에 없는 id는 만들지 않는다.

개념 목록 (id: 이름)
{concepts}

출력
- JSON 객체 하나만 출력한다. 형식: {{"코멘트 id": ["개념 id", ...]}}
- 입력한 모든 코멘트 id를 키로 넣는다.
- 설명, 코드 블록 표시 없이 JSON만 출력한다."""

USER_PROMPT = """아래 코멘트 {count}개를 분류해 줘. 각 항목은 코멘트 id, 파일 경로(path), 원문(body)이다.

{comments}"""


def system_prompt() -> str:
    concepts = "\n".join(f"- {concept.id}: {concept.name}" for concept in CONCEPTS)
    return SYSTEM_PROMPT.format(concepts=concepts)


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
        f"SELECT kind, {github_id}, pr_number, path, body, updated_at FROM comments "
        "WHERE mission_id = ? AND is_pr_author = 0 ORDER BY 1, 2",
        (mission_id,),
    ).fetchall()
    conn.close()
    return [{"kind": kind, "github_id": gid, "pr": pr, "path": path, "body": body, "updated_at": updated}
            for kind, gid, pr, path, body, updated in rows]


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
    classified_at = args.date or date.today().isoformat()
    path = save_ai_topics(AiTopics(
        mission_id=args.mission,
        model=",".join(sorted(m for m in models if MODEL in m)) or MODEL,
        entries={key: Entry(ids, classified_at, PROMPT_VERSION, CONCEPTS_VERSION) for key, ids in topics.items()},
    ))
    print(f"저장: {path}")


def edited_after(updated_at: str, classified_at: str) -> bool:
    """코멘트가 분류한 뒤에 고쳐졌는지. 분류 시각이 날짜뿐이면 날짜로 비교해, 그날 안에 고친 것은 보지 않는다."""
    updated = datetime.fromisoformat(updated_at)
    if len(classified_at) == len("2026-11-12"):
        return updated.astimezone(KST).date() > date.fromisoformat(classified_at)
    return updated > datetime.fromisoformat(classified_at)


def update_targets(comments: list[dict], fixed: AiTopics) -> tuple[list[dict], list[dict], int]:
    """(새 코멘트, 분류 뒤 고친 코멘트, 옛 버전 코멘트 수). 옛 버전 수에는 이번에 다시 분류할 코멘트를 넣지 않는다."""
    new, edited, stale = [], [], 0
    for comment in comments:
        entry = fixed.entries.get((comment["kind"], comment["github_id"]))
        if entry is None:
            new.append(comment)
        elif edited_after(comment["updated_at"], entry.classified_at):
            edited.append(comment)
        elif (entry.prompt_version, entry.concepts_version) != (PROMPT_VERSION, CONCEPTS_VERSION):
            stale += 1
    return new, edited, stale


def update(mission_id: str, limit: float | None, dry_run: bool = False, db: Path = DB,
           directory: Path = AI_TOPICS_DIR, cost_log: Path = COST_LOG, workers: int = WORKERS) -> dict:
    """고정본에 없거나 분류 뒤 고친 리뷰어 코멘트만 분류해 고정본에 덧붙인다. 다른 항목은 건드리지 않는다."""
    comments = reviewer_comments(mission_id, db)
    fixed = load_ai_topics(mission_id, directory) or AiTopics(mission_id=mission_id, model="")
    new, edited, stale = update_targets(comments, fixed)
    todo = new + edited
    summary = {"new": len(new), "edited": len(edited), "stale": stale, "saved": 0, "invalid": 0,
               "failed": [], "stopped": 0, "total_usd": 0.0}
    print(f"{mission_id}: 리뷰어 코멘트 {len(comments)}개, 고정본 {len(fixed.entries)}개", flush=True)
    print(f"  새 코멘트 {len(new)}개, 분류 뒤 고친 코멘트 {len(edited)}개 → 보낼 코멘트 {len(todo)}개 "
          f"(예상 약 {len(todo) * USD_PER_COMMENT:.2f}달러)", flush=True)
    print(f"  옛 버전 코멘트 {stale}개 (다시 분류하지 않는다. 지금 프롬프트 {PROMPT_VERSION}, 개념 목록 {CONCEPTS_VERSION})",
          flush=True)
    if dry_run or not todo:
        return summary

    concept_ids = {c.id for c in CONCEPTS}
    system = system_prompt()
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    budget = Budget(f"update:{mission_id}", limit, cost_log)
    lock = threading.Lock()
    started = time.time()

    def work(n: int) -> None:
        batch = batches[n]
        try:
            labels, models = classify_batch(budget, f"{mission_id} update #{n}", system, batch)
        except BudgetReached as reached:
            with lock:
                summary["stopped"] += 1
            print(f"멈춤 (비용 상한) #{n}: {reached}", flush=True)
            return
        except RuntimeError as error:
            with lock:
                summary["failed"].append({"batch": n, "error": str(error)})
            print(f"실패 #{n}: {error}", flush=True)
            return
        classified_at = datetime.now(KST).isoformat(timespec="seconds")
        with lock:
            for comment in batch:
                topics = labels[str(comment["github_id"])]
                topics = topics if isinstance(topics, list) else []
                summary["invalid"] += sum(1 for t in topics if t not in concept_ids)
                fixed.entries[(comment["kind"], comment["github_id"])] = Entry(
                    sorted({t for t in topics if t in concept_ids}), classified_at, PROMPT_VERSION, CONCEPTS_VERSION)
            known = {m for m in fixed.model.split(",") if m}
            fixed.model = ",".join(sorted(known | {m for m in models if MODEL in m})) or MODEL
            # 묶음마다 고정본에 바로 쓴다. 끊겨도 여기까지 분류한 코멘트는 다음 실행의 대상에서 빠진다.
            save_ai_topics(fixed, directory)
            summary["saved"] += len(batch)
        print(f"#{n} 저장 ({time.time() - started:.0f}s, 누적 {budget.total:.3f}달러)", flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, range(len(batches))))
    summary["total_usd"] = budget.total
    print(f"끝: {time.time() - started:.0f}s, 고정본에 쓴 코멘트 {summary['saved']}/{len(todo)}개, "
          f"누적 {budget.total:.3f}달러, 버린 id {summary['invalid']}개, "
          f"실패 묶음 {len(summary['failed'])}, 상한으로 멈춘 묶음 {summary['stopped']}")
    return summary


def cmd_update(args) -> None:
    update(args.mission, args.limit, args.dry_run)


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
    p = sub.add_parser("update")
    p.add_argument("mission")
    p.add_argument("--limit", type=float, help="이 미션 증분 분류의 누적 비용 상한(달러). --dry-run이 아니면 꼭 준다")
    p.add_argument("--dry-run", action="store_true", help="AI를 부르지 않고 대상 수와 예상 비용만 보여 준다")
    p.set_defaults(func=cmd_update)
    args = parser.parse_args()
    if args.cmd == "update" and not args.dry_run and args.limit is None:
        parser.error("update는 --limit이 필요하다 (--dry-run일 때만 빼도 된다)")
    args.func(args)


if __name__ == "__main__":
    main()
