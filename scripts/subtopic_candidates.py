"""세부 지적 후보 찾기. AI 분류 고정본에서 PR 수 상위 개념을 골라 claude -p로 후보를 뽑는다.

    uv run python -m scripts.subtopic_candidates find java-calculator --limit 2          # 후보 뽑기 + 코멘트 배정
    uv run python -m scripts.subtopic_candidates overlaps java-calculator                # 합칠 만한 후보 쌍 (AI 호출 없음)
    uv run python -m scripts.subtopic_candidates check java-calculator --limit 2         # 합친 뒤 의견 갈림 입장 확인
    uv run python -m scripts.subtopic_candidates build java-calculator                   # 결과를 한 파일로

방법은 로또 세부 지적 후보(2026-11-12)와 같다. 결과는 data/ai/<mission>/subtopics/에 두고 (git 밖),
합칠 후보는 data/ai/<mission>/subtopics/merges.json에 사람이(또는 에이전트가) 적는다.
topics.py에는 넣지 않는다. 채택하면 build 결과의 (kind, github_id) 목록으로 고정본에 바로 붙인다.
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

from cholog_mcp.missions import MISSIONS
from pipeline.ai_store import load_ai_topics
from pipeline.topics import CONCEPTS
from scripts.ai_budget import Budget, BudgetReached, call_claude
from scripts.ai_classify import BATCH, OUT, USER_PROMPT, parse, reviewer_comments

MODEL = "sonnet"
WORKERS = 5
TRIES = 2
TOP_CONCEPTS = 4
BODY_LIMIT = 800  # 후보 뽑기 호출에서 코멘트 하나당 넣는 최대 글자 수
COMMENT_LIMIT = 3000  # 입장 확인 호출에서 코멘트 하나당 넣는 최대 글자 수

CANDIDATE_PROMPT = """너는 초록스터디 리드를 돕는다. {mission}({mission_id}) 미션 PR에 리뷰어가 남긴 코드 리뷰 코멘트 중
'{name}'({id}) 개념으로 분류된 코멘트를 전부 준다. 각 항목은 코멘트 id, PR 번호(pr), 파일 경로(path), 원문(body)이다.
원문이 길면 앞 {limit}자만 넣었다.

할 일: 이 미션에서 여러 PR에 반복해서 나오는 구체적인 세부 지적을 3~6개 후보로 묶는다.
- 세부 지적은 개념을 다시 말한 것(예: "책임을 분리하라")이 아니라 이 미션 코드의 구체적인 지점이어야 한다.
  좋은 예(자동차 경주 미션): "인터페이스를 만들고 내부에서 new (주입 안 됨)", "Random 객체를 매번 new"
  좋은 예(로또 미션): "getter로 번호를 꺼내 외부에서 당첨 판정", "로또 번호를 Integer로 둠 (LottoNumber 미포장)"
- 여러 PR에서 반복되는 것만 고른다.
- 후보마다 아래를 적는다.
  - id: 영어 kebab-case
  - name: 짧은 한국어 이름
  - description: 한 줄 설명
  - disagreement: 리뷰어끼리 의견이 갈리면 {{"split": true, "sides": [{{"stance": "입장 한 줄", "prs": [PR 번호, ...]}}, ...]}}, 갈리지 않으면 {{"split": false}}

출력: JSON 객체 하나만. 형식: {{"candidates": [{{"id": ..., "name": ..., "description": ..., "disagreement": ...}}, ...]}}
설명, 코드 블록 표시 없이 JSON만 출력한다."""

ASSIGN_PROMPT = """너는 {mission}({mission_id}) 미션 PR에 리뷰어가 남긴 코드 리뷰 코멘트를 세부 지적으로 분류한다.
코멘트는 모두 '{name}'({id}) 개념으로 분류된 것이다. 각 코멘트가 아래 세부 지적 후보 중 어디에 해당하는지 후보 id를 붙인다.

규칙
- 여러 개면 모두 적는다. 해당하는 후보가 없으면 빈 배열.
- 목록에 없는 id는 만들지 않는다.

세부 지적 후보 (id: 이름 - 설명)
{candidates}

출력
- JSON 객체 하나만 출력한다. 형식: {{"코멘트 id": ["후보 id", ...]}}
- 입력한 모든 코멘트 id를 키로 넣는다.
- 설명, 코드 블록 표시 없이 JSON만 출력한다."""

VERIFY_PROMPT = """너는 코드 리뷰 기록을 확인한다. {mission}({mission_id}) 미션 PR #{pr}에 리뷰어가 남긴 코멘트를 전부 준다.
각 항목은 코멘트 id, 파일 경로(path), 원문(body)이다. 원문이 길면 앞 {limit}자만 넣었다.

확인할 것: 아래 입장이 이 PR의 리뷰어 코멘트에 실제로 나타나는가.
- 세부 지적: {name} - {description}
- 입장: {stance}

판단 기준
- 리뷰어가 이 세부 지적에 대해 이 입장(또는 같은 뜻)을 말한 코멘트가 있으면 "확인".
- 그런 코멘트가 없거나, 반대 입장만 있으면 "불일치".

출력: JSON 객체 하나만. 형식: {{"verdict": "확인" 또는 "불일치", "comment_id": 근거 코멘트 id 또는 null, "reason": "한 줄 근거"}}
설명, 코드 블록 표시 없이 JSON만 출력한다."""


def _dir(mission_id: str) -> Path:
    return OUT / mission_id / "subtopics"


def _key(comment: dict) -> str:
    return f"{comment['kind']}:{comment['github_id']}"


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def ask_json(budget: Budget, label: str, kind: str, system: str, user: str, expected: set[str]) -> dict:
    """JSON 객체를 받는다. 실패하면 한 번만 다시 보낸다."""
    last = None
    for attempt in range(TRIES):
        try:
            result = call_claude(budget, f"{label} try{attempt + 1}", MODEL, system, user, kind)
            data = parse(result.get("result", ""))
            if not isinstance(data, dict) or not expected <= set(map(str, data)):
                raise ValueError("빠진 키 또는 형식 오류")
            return data
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            last = error
    raise RuntimeError(f"{TRIES}번 시도해도 실패: {last}")


def tagged_comments(mission_id: str) -> dict[str, list[dict]]:
    """개념별로 AI 고정본에서 그 개념이 붙은 리뷰어 코멘트."""
    fixed = load_ai_topics(mission_id)
    if fixed is None:
        raise SystemExit(f"AI 고정본이 없다: {mission_id}")
    by_concept: dict[str, list[dict]] = {c.id: [] for c in CONCEPTS}
    for comment in reviewer_comments(mission_id):
        for topic in fixed.topics.get((comment["kind"], comment["github_id"]), []):
            if topic in by_concept:
                by_concept[topic].append(comment)
    return by_concept


def top_concepts(by_concept: dict[str, list[dict]], count: int = TOP_CONCEPTS) -> list[str]:
    def prs(concept_id: str) -> int:
        return len({c["pr"] for c in by_concept[concept_id]})
    return sorted(by_concept, key=lambda cid: (-prs(cid), -len(by_concept[cid]), cid))[:count]


def cmd_find(args) -> None:
    mission = MISSIONS[args.mission]
    by_concept = tagged_comments(args.mission)
    concept_ids = args.concepts or top_concepts(by_concept)
    names = {c.id: c.name for c in CONCEPTS}
    out = _dir(args.mission)
    budget = Budget(f"subtopics:{args.mission}", args.limit)
    started = time.time()
    print(f"개념: {concept_ids}", flush=True)
    fmt = {"mission": mission.name, "mission_id": mission.id}

    def find(concept_id: str) -> None:
        path = out / f"candidates-{concept_id}.json"
        if path.exists():
            return
        comments = by_concept[concept_id]
        system = CANDIDATE_PROMPT.format(**fmt, name=names[concept_id], id=concept_id, limit=BODY_LIMIT)
        items = [{"id": c["github_id"], "pr": c["pr"], "path": c["path"], "body": c["body"][:BODY_LIMIT]}
                 for c in comments]
        user = f"코멘트 {len(items)}개:\n\n" + json.dumps(items, ensure_ascii=False)
        data = ask_json(budget, f"candidates {concept_id}", "candidates", system, user, {"candidates"})
        _write(path, {"concept": concept_id, "candidates": data["candidates"]})
        print(f"후보 {concept_id}: {len(data['candidates'])}개 ({time.time() - started:.0f}s, 누적 {budget.total:.3f})",
              flush=True)

    def assign(job: tuple[str, int]) -> None:
        concept_id, n = job
        path = out / f"assign-{concept_id}-{n:04d}.json"
        if path.exists():
            return
        candidates = json.loads((out / f"candidates-{concept_id}.json").read_text())["candidates"]
        listing = "\n".join(f"- {c['id']}: {c['name']} - {c['description']}" for c in candidates)
        system = ASSIGN_PROMPT.format(**fmt, name=names[concept_id], id=concept_id, candidates=listing)
        batch = by_concept[concept_id][n * BATCH:(n + 1) * BATCH]
        items = [{"id": c["github_id"], "path": c["path"], "body": c["body"]} for c in batch]
        user = USER_PROMPT.format(count=len(items), comments=json.dumps(items, ensure_ascii=False, indent=1))
        expected = {str(c["github_id"]) for c in batch}
        labels = ask_json(budget, f"assign {concept_id} #{n}", "assign", system, user, expected)
        valid = {c["id"] for c in candidates}
        subs = {_key(c): labels[str(c["github_id"])] for c in batch}
        subs = {key: value if isinstance(value, list) else [] for key, value in subs.items()}
        _write(path, {key: sorted({s for s in value if s in valid}) for key, value in subs.items()}
               | {"_invalid": [s for value in subs.values() for s in value if s not in valid]})

    def safe(fn, item):
        try:
            fn(item)
        except BudgetReached as reached:
            print(f"멈춤 (비용 상한) {item}: {reached}", flush=True)
        except RuntimeError as error:
            print(f"실패 {item}: {error}", flush=True)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(lambda cid: safe(find, cid), concept_ids))
        jobs = [(cid, n) for cid in concept_ids if (out / f"candidates-{cid}.json").exists()
                for n in range((len(by_concept[cid]) + BATCH - 1) // BATCH)]
        list(pool.map(lambda job: safe(assign, job), jobs))
    _write(out / "find-status.json", {"concepts": concept_ids, "wall_seconds": round(time.time() - started, 1),
                                      "total_usd": budget.total})
    print(f"끝: {time.time() - started:.0f}s, 누적 {budget.total:.3f}달러")


def collect(mission_id: str) -> dict[str, dict]:
    """개념별 후보와, 후보마다 붙은 코멘트 키 목록."""
    out = _dir(mission_id)
    status = json.loads((out / "find-status.json").read_text())
    by_concept = tagged_comments(mission_id)
    result = {}
    for concept_id in status["concepts"]:
        candidates = json.loads((out / f"candidates-{concept_id}.json").read_text())["candidates"]
        assignments, invalid, batches = {}, [], 0
        for path in sorted(out.glob(f"assign-{concept_id}-*.json")):
            data = json.loads(path.read_text())
            invalid.extend(data.pop("_invalid"))
            assignments.update(data)
            batches += 1
        for candidate in candidates:
            candidate["comments"] = sorted(k for k, subs in assignments.items() if candidate["id"] in subs)
        result[concept_id] = {"tagged_comments": len(by_concept[concept_id]), "assigned_comments": len(assignments),
                              "assign_batches": batches, "invalid_ids": invalid, "candidates": candidates,
                              "unassigned": sum(1 for subs in assignments.values() if not subs)}
    return result


def cmd_overlaps(args) -> None:
    """다른 후보와 코멘트가 많이 겹치는 쌍. 작은 쪽 코멘트의 몇 %가 겹치는지 본다."""
    found = collect(args.mission)
    flat = [(cid, c) for cid, concept in found.items() for c in concept["candidates"]]
    pairs = []
    for (ca, a), (cb, b) in combinations(flat, 2):
        shared = set(a["comments"]) & set(b["comments"])
        small = min(len(a["comments"]), len(b["comments"])) or 1
        if shared:
            pairs.append((len(shared) / small, len(shared), f"{ca}/{a['id']}", f"{cb}/{b['id']}"))
    for ratio, shared, a, b in sorted(pairs, reverse=True)[: args.top]:
        print(f"{ratio:4.0%}  겹침 {shared:3d}  {a}  ~  {b}")


def _merged(mission_id: str) -> list[dict]:
    """merges.json을 적용한 후보 목록. merges.json 형식:
    {"merges": [{"key": "①", "into": 개념, "parts": ["개념/후보", ...]}], "discard": {"개념/후보": "이유"}}"""
    found = collect(mission_id)
    pr_of = {_key(c): c["pr"] for c in reviewer_comments(mission_id)}
    path = _dir(mission_id) / "merges.json"
    merges = json.loads(path.read_text()) if path.exists() else {"merges": [], "discard": {}}
    by_ref = {f"{cid}/{c['id']}": (cid, c) for cid, concept in found.items() for c in concept["candidates"]}
    used = {part for merge in merges["merges"] for part in merge["parts"]}
    items = []
    for merge in merges["merges"]:
        parts = [by_ref[p] for p in merge["parts"]]
        first = next(c for cid, c in parts if cid == merge["into"])
        sides = [dict(side, source=f"{cid}/{c['id']}") for cid, c in parts
                 for side in ((c.get("disagreement") or {}).get("sides") or [])]
        items.append({"key": merge["key"], "concept": merge["into"], "parts": merge["parts"], "name": first["name"],
                      "description": first["description"],
                      "comments": sorted({k for _, c in parts for k in c["comments"]}), "sides": sides})
    for ref, (cid, c) in by_ref.items():
        if ref in used:
            continue
        sides = [dict(side, source=ref) for side in ((c.get("disagreement") or {}).get("sides") or [])]
        items.append({"key": c["id"], "concept": cid, "parts": [ref], "name": c["name"],
                      "description": c["description"], "comments": c["comments"], "sides": sides,
                      "discarded": merges["discard"].get(ref)})
    for item in items:
        item["comment_count"] = len(item["comments"])
        item["pr_count"] = len({pr_of[k] for k in item["comments"]})
    return items


def cmd_check(args) -> None:
    mission = MISSIONS[args.mission]
    comments = reviewer_comments(args.mission)
    by_pr: dict[int, list[dict]] = {}
    for c in comments:
        by_pr.setdefault(c["pr"], []).append(c)
    items = [item for item in _merged(args.mission) if not item.get("discarded")]
    jobs = [(item, s, side, pr) for item in items for s, side in enumerate(item["sides"]) for pr in side["prs"]]
    # 비용 상한으로 중간에 멈춰도 후보마다 몇 건씩은 확인되도록 후보를 번갈아 보낸다.
    position = {}
    for job in jobs:
        position[id(job)] = sum(1 for other in jobs if other[0] is job[0] and id(other) in position)
    jobs.sort(key=lambda job: position[id(job)])
    out = _dir(args.mission) / "checks"
    budget = Budget(f"subtopics:{args.mission}", args.limit)
    started = time.time()

    def check(job) -> None:
        item, s, side, pr = job
        path = out / f"{item['concept']}--{item['key']}--{s}--{pr}.json"
        if path.exists():
            return
        pr_comments = by_pr.get(pr, [])
        if not pr_comments:
            _write(path, {"verdict": "코멘트 없음"})
            return
        system = VERIFY_PROMPT.format(mission=mission.name, mission_id=mission.id, pr=pr, limit=COMMENT_LIMIT,
                                      name=item["name"], description=item["description"], stance=side["stance"])
        user = json.dumps([{"id": c["github_id"], "path": c["path"], "body": c["body"][:COMMENT_LIMIT]}
                           for c in pr_comments], ensure_ascii=False, indent=1)
        try:
            verdict = ask_json(budget, f"check {item['key']} PR {pr}", "check", system, user, {"verdict"})
        except BudgetReached as reached:
            print(f"멈춤 (비용 상한) {item['key']} PR {pr}: {reached}", flush=True)
            return
        except RuntimeError as error:
            print(f"실패 {item['key']} PR {pr}: {error}", flush=True)
            return
        _write(path, verdict)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(check, jobs))
    print(f"확인 {len(jobs)}건, {time.time() - started:.0f}s, 누적 {budget.total:.3f}달러")


def cmd_build(args) -> None:
    out = _dir(args.mission)
    items = _merged(args.mission)
    for item in items:
        for s, side in enumerate(item["sides"]):
            side["checks"] = []
            for pr in side["prs"]:
                path = out / "checks" / f"{item['concept']}--{item['key']}--{s}--{pr}.json"
                side["checks"].append({"pr": pr, **(json.loads(path.read_text()) if path.exists()
                                                    else {"verdict": "확인 안 함"})})
            side["kept_prs"] = [c["pr"] for c in side["checks"] if c["verdict"] == "확인"]
    found = collect(args.mission)
    _write(out / "result.json", {
        "mission_id": args.mission, "model": MODEL,
        "concepts": {cid: {k: v for k, v in concept.items() if k != "candidates"} for cid, concept in found.items()},
        "candidates": items,
        "prompts": {"candidate": CANDIDATE_PROMPT, "assign": ASSIGN_PROMPT, "verify": VERIFY_PROMPT},
    })
    print(f"저장: {out / 'result.json'} (후보 {len(items)}개)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("find")
    p.add_argument("mission")
    p.add_argument("--concepts", nargs="+")
    p.add_argument("--limit", type=float, required=True, help="세부 지적 단계의 누적 비용 상한(달러)")
    p.set_defaults(func=cmd_find)
    p = sub.add_parser("overlaps")
    p.add_argument("mission")
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(func=cmd_overlaps)
    p = sub.add_parser("check")
    p.add_argument("mission")
    p.add_argument("--limit", type=float, required=True)
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("build")
    p.add_argument("mission")
    p.set_defaults(func=cmd_build)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
