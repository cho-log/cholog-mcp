from typing import get_args

from cholog_mcp.missions import MISSIONS, MissionId


def test_입력으로_받는_미션과_미션_목록이_같다():
    assert set(get_args(MissionId)) == set(MISSIONS)
