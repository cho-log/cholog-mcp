"""지원하는 미션. 미션을 추가할 때 여기에 한 줄을 더한다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Mission:
    id: str
    repo: str
    name: str


MISSIONS = {
    mission.id: mission
    for mission in (
        Mission(
            id="java-racingcar",
            repo="next-step/java-racingcar-simple-playground",
            name="자바 자동차 경주",
        ),
    )
}
