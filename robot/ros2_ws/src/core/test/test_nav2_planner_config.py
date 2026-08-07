"""Nav2 전역 경로 계획기 설정을 검증한다."""

from pathlib import Path

import yaml


def test_navfn_planner_uses_astar():
    """전역 NavFn 경로 계획기가 A* 탐색을 사용하도록 설정됐는지 확인한다."""
    config_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "nav2_safe_params.yaml"
    )

    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    grid_based = config["planner_server"]["ros__parameters"]["GridBased"]

    assert grid_based["plugin"] == "nav2_navfn_planner/NavfnPlanner"
    assert grid_based["use_astar"] is True
