# Pico H 펌웨어

`closed_loop_speed.py`는 목표 회전 속도(rev/s)를 받아 엔코더 피드백으로 PWM을
맞추는 폐루프 속도 제어 펌웨어입니다. MicroPython으로 작성했습니다.

Jetson의 ROS 2 노드와 주고받는 형식은
[`../docs/pico-serial-protocol.md`](../docs/pico-serial-protocol.md)가 정합니다.
한쪽을 바꿀 때는 그 문서를 먼저 고칩니다.

Jetson의 `~/test/closed_loop_speed.py`에서 반입했습니다. 앞으로는 이 파일을
기준으로 하고 Jetson 사본은 쓰지 않습니다.

## 올리기

Jetson에서 `mpremote`로 올립니다. Pico는 `/dev/ttyACM0`으로 잡힙니다.

| 목적 | 명령 |
| --- | --- |
| 한 번만 실행 (플래시에 남기지 않음) | `mpremote connect /dev/ttyACM0 run closed_loop_speed.py` |
| 플래시에 파일만 올리기 | `mpremote connect /dev/ttyACM0 cp closed_loop_speed.py :` |
| 시리얼 콘솔 열기 | `mpremote connect /dev/ttyACM0 repl` |

`run`은 RAM에서 실행하므로 `mpremote`를 끝내면 프로그램도 끝납니다.

플래시에 같은 이름의 파일이 있으면 `cp`는 그대로 덮어씁니다. 이전 시험에서 올린
파일이 남아 있을 수 있으니 확인하고 필요하면 백업합니다.
