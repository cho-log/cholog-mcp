"""GitHub에서 미션의 PR과 코멘트를 내려받아 data/raw/<mission>/에 저장한다.

GitHub CLI(`gh`)를 쓴다. 먼저 `gh auth login`으로 로그인해 둔다.
PR 하나에 API를 2번 부른다 (코드 줄 리뷰, PR 대화).
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

from cholog_mcp.missions import Mission

PR_FIELDS = "additions,author,baseRefName,changedFiles,createdAt,deletions,number,state,title"
# GitHub API 경로: 코드 줄에 단 리뷰는 pulls, PR 대화는 issues 아래에 있다.
COMMENT_ENDPOINTS = {"review": "pulls", "issue": "issues"}


def _gh(*args: str) -> str:
    return subprocess.run(("gh", *args), check=True, capture_output=True, text=True).stdout


def fetch_mission(mission: Mission, raw_dir: Path, only: list[int] | None = None) -> int:
    """미션의 PR 목록과 코멘트를 받는다. only를 주면 그 PR의 코멘트만 받는다. 받은 PR 수를 돌려준다."""
    fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
    raw_dir.mkdir(parents=True, exist_ok=True)

    prs_json = _gh("pr", "list", "--repo", mission.repo, "--state", "all", "--limit", "5000", "--json", PR_FIELDS)
    (raw_dir / "prs.json").write_text(prs_json, encoding="utf-8")

    numbers = [pr["number"] for pr in json.loads(prs_json)]
    if only is not None:
        numbers = [number for number in numbers if number in only]

    for kind, endpoint in COMMENT_ENDPOINTS.items():
        (raw_dir / kind).mkdir(exist_ok=True)
        for number in numbers:
            comments = _gh("api", "--paginate", f"repos/{mission.repo}/{endpoint}/{number}/comments?per_page=100")
            (raw_dir / kind / f"{number}.json").write_text(comments, encoding="utf-8")

    (raw_dir / "meta.json").write_text(json.dumps({"fetched_at": fetched_at}), encoding="utf-8")
    return len(numbers)
