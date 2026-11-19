"""claude -p 호출과 비용 상한 (AI 분류 스크립트가 같이 쓴다).

- 호출마다 --max-budget-usd를 붙인다.
- --output-format json의 total_cost_usd를 단계별로 누적해 data/ai-cost-log.json에 남긴다.
- 단계 누적이 상한의 90%에 닿으면 새 호출을 보내지 않는다. 동시에 나가 있는 호출도
  지금까지 가장 비쌌던 호출만큼 든다고 미리 잡아 두고 계산한다.
"""

import json
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

COST_LOG = Path("data/ai-cost-log.json")
MAX_BUDGET_PER_CALL = 0.50
STOP_RATIO = 0.9
MIN_RESERVE = 0.05  # 아직 호출 기록이 없을 때 호출 하나에 미리 잡아 두는 비용


class BudgetReached(Exception):
    pass


class Budget:
    def __init__(self, step: str, limit: float, log_path: Path = COST_LOG):
        self.step, self.limit, self.log_path = step, limit, log_path
        self._lock = threading.Lock()
        self._in_flight = 0
        log = self._read()
        entry = log["steps"].setdefault(step, {"limit_usd": limit, "total_usd": 0.0, "calls": []})
        entry["limit_usd"] = limit
        self._write(log)

    def _read(self) -> dict:
        if self.log_path.exists():
            return json.loads(self.log_path.read_text(encoding="utf-8"))
        return {"steps": {}}

    def _write(self, log: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")

    def _entry(self) -> dict:
        return self._read()["steps"][self.step]

    @property
    def total(self) -> float:
        return self._entry()["total_usd"]

    def _reserve(self) -> float:
        costs = [call["cost_usd"] for call in self._entry()["calls"]]
        return max([MIN_RESERVE, *costs])

    def acquire(self) -> None:
        """새 호출을 보내도 되는지 본다. 안 되면 BudgetReached."""
        with self._lock:
            reserve = self._reserve()
            if self.total + (self._in_flight + 1) * reserve >= self.limit * STOP_RATIO:
                raise BudgetReached(f"{self.step}: 누적 {self.total:.3f}달러, 상한 {self.limit}달러의 90%")
            self._in_flight += 1

    def record(self, label: str, result: dict | None, error: str | None, wall_s: float) -> None:
        with self._lock:
            self._in_flight -= 1
            log = self._read()
            entry = log["steps"][self.step]
            usage = (result or {}).get("usage") or {}
            cost = (result or {}).get("total_cost_usd") or 0.0
            entry["calls"].append({
                "label": label,
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "cost_usd": cost,
                "wall_s": round(wall_s, 1),
                "models": list(((result or {}).get("modelUsage") or {}).keys()),
                "input": usage.get("input_tokens", 0),
                "cache_creation": usage.get("cache_creation_input_tokens", 0),
                "cache_read": usage.get("cache_read_input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "error": error,
            })
            entry["total_usd"] = round(entry["total_usd"] + cost, 6)
            self._write(log)


def call_claude(budget: Budget, label: str, model: str, system: str, user: str, timeout: int = 900) -> dict:
    """claude -p를 도구·설정·MCP 없이 빈 폴더에서 한 번 부른다. 결과 JSON을 돌려준다."""
    budget.acquire()
    started, result, error = time.time(), None, None
    try:
        # 프로젝트 CLAUDE.md 등이 끼어들지 않게 빈 폴더에서 돌린다.
        with tempfile.TemporaryDirectory() as cwd:
            completed = subprocess.run(
                ["claude", "-p", "--model", model, "--output-format", "json", "--tools", "",
                 "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
                 "--max-budget-usd", f"{MAX_BUDGET_PER_CALL:.2f}", "--system-prompt", system],
                input=user, capture_output=True, text=True, cwd=cwd, timeout=timeout,
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result = None
        if completed.returncode != 0 or result is None or result.get("is_error"):
            detail = (result or {}).get("subtype") or completed.stderr[-300:] or completed.stdout[-300:]
            error = f"종료 코드 {completed.returncode}: {detail}"
            raise RuntimeError(error)
        return result
    except subprocess.TimeoutExpired as timeout_error:
        error = f"시간 초과 {timeout}초"
        raise RuntimeError(error) from timeout_error
    finally:
        budget.record(label, result, error, time.time() - started)
