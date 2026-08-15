# CLAUDE.md

이 프로젝트에서 작업하기 전에 [`AGENTS.md`](AGENTS.md)를 읽고 해당 규칙을 따른다. 작업 규칙의 원본은 `AGENTS.md`이며 이 문서와 내용이 다르면 `AGENTS.md`를 우선한다.

건드리는 곳에 따라 함께 읽을 문서가 다르다.

| 건드리는 곳 | 함께 읽을 문서 |
| --- | --- |
| `ros2_ws/**` 전반 | [`AGENTS.md`](AGENTS.md) |
| 이동·주행·실제 차량 하드웨어 | [`docs/hardware-control.md`](docs/hardware-control.md), [`docs/pico-serial-protocol.md`](docs/pico-serial-protocol.md) |
| `ai_vision/**` | [`ai_vision/AGENTS.md`](ai_vision/AGENTS.md)와 그 문서가 지정한 설계 문서 |
| `ai_chat/**` | 저장소 루트 [`CLAUDE.md`](../CLAUDE.md), [`ai_chat/README.md`](ai_chat/README.md) |

`ai_chat/`은 ROS 2 패키지가 아니라 독립 Python 패키지이므로 `AGENTS.md`의 적용 대상이 아니다. 대화 런타임의 설계 근거는 [`임시보류_claude.md`](../임시보류_claude.md)에 보관돼 있다.

**커밋 규율: 한 커밋은 한 라인의 경로만 건드린다.** `robot/ai_chat/**` ↔ `ros2_ws/**` ↔ `backend/**`를 한 커밋에 섞지 않는다. 저장소 루트 `CLAUDE.md`의 예외 없는 규칙이다.
