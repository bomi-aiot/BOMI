# 0001. Nav2RobotDriver가 NavigateToPose 액션 클라이언트를 직접 소유한다

- 상태: 채택 (Accepted)
- 관련: S15P11E102-164 (MQTT 브릿지), S15P11E102-79 (Nav2 waypoint 순찰)

## 문제 상황

브릿지의 `RobotDriver` 실물 구현이 실제 로봇 주행을 어떻게 실행할지 결정해야 한다.
백엔드 명령(NAVIGATE target=ENTRANCE/DEFAULT)을 실제 Nav2 이동으로 옮기는 방법에
두 가지 선택지가 있었다.

## 검토한 선택지

- **옵션 A**: 브릿지가 `/bomi/nav/goal`(이름)을 발행하고 `/bomi/nav/result`를
  구독한다. 별도의 주행 노드(강현 소유)가 이 토픽을 받아 Nav2를 호출한다.
  두 노드 사이에 ROS 2 토픽 계약을 새로 합의해야 한다.
- **옵션 B**: 브릿지의 `Nav2RobotDriver`가 `NavigateToPose` 액션 클라이언트를
  직접 소유한다. 강현 `S15P11E102-79`의 검증된 패턴(`nav2_waypoint_patrol.py`,
  `waypoint_route.py`)을 이식하고, target 이름을 좌표로 변환해 Nav2에 바로 목표를
  보낸다. 별도 토픽 핸드셰이크가 없다.

## 결정

**옵션 B를 채택한다.**

## 이유

- 강현 코드에 `NavigateToPose` 액션 클라이언트, pose/quaternion 생성, YAML 좌표
  로딩이 이미 검증된 형태로 존재한다. 이식 대상이 명확하다.
- 중간 토픽 계약(A)을 새로 정의·유지하지 않아 결합면이 줄고, 브릿지가 도착 상태를
  직접 받으므로 결과 발행 흐름이 단순하다.
- 강현이 하드웨어 조립 중이라, 노드 간 토픽 합의를 기다리지 않고 독립적으로
  진행할 수 있다.

## 남는 조율 사항 (강현과)

- ENTRANCE/DEFAULT의 실제 좌표는 `room_waypoints.yaml`(강현 소유)이 기준이다.
  해당 값 또는 파일을 공유받아 이름→좌표 변환에 사용한다.
- 브릿지 드라이버와 강현 순찰 노드가 동시에 Nav2에 상반된 목표를 보내지 않도록
  실행 시점을 정리한다.

## 현재 범위에 대한 영향

- 지금은 `MockRobotDriver`만 사용한다. 실물 `Nav2RobotDriver`는 하드웨어와 Nav2가
  준비된 시점에 이 결정에 따라 구현한다. 그전까지 빈 골격을 두지 않는다
  (로봇 `AGENTS.md`: 미래 기능 선구현 금지).
- 전환 지점은 브릿지에 주입하는 드라이버 한 줄(`MockRobotDriver()` →
  `Nav2RobotDriver()`)이며, 브릿지 코어·계약 코드는 바뀌지 않는다.
