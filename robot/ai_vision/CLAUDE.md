# CLAUDE.md

이 프로젝트에서 작업하기 전에 [`AGENTS.md`](AGENTS.md)를 읽고 해당 규칙을 따른다.

추가로 다음 문서를 "사실 → 규칙 → 설계" 순으로 참고한다.

- [`README.md`](README.md) — **구현 사실의 기준.** 무엇이 실제로 도는지는 여기와 소스를 본다.
- [`docs/code-style.md`](docs/code-style.md) — 주석·docstring·명명 규칙
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — 계층 경계와 의존성 규칙
- [`docs/vision-requirements.md`](docs/vision-requirements.md) — 기능 요구사항
- [`docs/state-machine.md`](docs/state-machine.md) — 상태와 전환 규칙

뒤의 세 문서(`ARCHITECTURE.md`, `docs/vision-requirements.md`, `docs/state-machine.md`)는 **목표 상태를 기술하며 미구현 설계를 포함한다.** 특히 사용자 상태 머신(`AWAKE`/`RESTING`/`SLEEPING_ESTIMATED`), `interaction_allowed`·`movement_allowed` 출력, YAML 설정 계층, ROS 2 노드는 현재 코드에 없다. 문서와 코드가 어긋나면 임의로 맞추지 말고 `README.md`와 소스를 사실로 삼은 뒤 충돌을 기록한다.

작업을 시작하기 전에 알아 둘 두 가지가 있다.

- `make check`는 **현재 실패한다.** `make check-docstrings`가 기존 34건의 docstring 위반(대부분 `tests/test_primary_person.py`)을 잡기 때문이며 당신의 변경 탓이 아니다. 판단 기준은 "내 변경이 새 위반을 추가하지 않았는가"다.
- 테스트는 프로젝트 루트에서 `python -m pytest`로 실행한다. `conftest.py`가 없어 일부 테스트가 `from scripts...` 형태로 import하므로 현재 작업 디렉터리가 `sys.path`에 들어가야 한다.
