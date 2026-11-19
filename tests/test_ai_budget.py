"""AI 호출 비용 상한 (scripts/ai_budget.py)."""

import json

import pytest

from scripts.ai_budget import Budget, BudgetReached


def _spend(budget: Budget, cost: float) -> None:
    budget.acquire()
    budget.record("call", {"total_cost_usd": cost}, None, 1.0)


def test_비용은_단계별로_누적해_파일에_남긴다(tmp_path):
    log = tmp_path / "ai-cost-log.json"
    budget = Budget("classify:test", 3.0, log)

    _spend(budget, 0.1)
    _spend(budget, 0.2)

    data = json.loads(log.read_text())
    assert data["steps"]["classify:test"]["total_usd"] == pytest.approx(0.3)
    assert len(data["steps"]["classify:test"]["calls"]) == 2


def test_누적이_상한의_90퍼센트에_닿으면_새_호출을_보내지_않는다(tmp_path):
    budget = Budget("classify:test", 1.0, tmp_path / "log.json")
    _spend(budget, 0.8)

    # 다음 호출을 지금까지 가장 비쌌던 호출(0.8)만큼으로 잡으면 90%를 넘는다.
    with pytest.raises(BudgetReached):
        budget.acquire()


def test_다시_실행해도_앞선_누적을_이어서_센다(tmp_path):
    log = tmp_path / "log.json"
    _spend(Budget("classify:test", 1.0, log), 0.5)

    again = Budget("classify:test", 1.0, log)

    assert again.total == pytest.approx(0.5)
    with pytest.raises(BudgetReached):
        again.acquire()


def test_미리_잡아_두는_비용은_같은_종류의_호출로_정한다(tmp_path):
    budget = Budget("subtopics:test", 1.5, tmp_path / "log.json")
    budget.acquire("candidates")
    budget.record("큰 호출", {"total_cost_usd": 0.6}, None, 1.0, "candidates")

    # 작은 호출은 큰 호출 비용(0.6)이 아니라 기본값(0.05)으로 잡는다.
    for _ in range(5):
        budget.acquire("assign")
    with pytest.raises(BudgetReached):
        budget.acquire("candidates")
