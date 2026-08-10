# 시연 기본값. ~/.bomi_demo_state 가 없을 때 bomi_goto.sh 가 여기서 읽는다.
# 확장자가 .sh 인 이유: .gitignore 의 **/*.env 규칙에 걸려 저장소에 안 들어가면
# 폴백이 무용지물이 된다. 비밀값이 없으므로 규칙에 예외를 뚫지 않고 이름을 바꿨다.
#
# 왜 저장소에 두는가: 상태 파일은 젯슨 홈에만 있는 런타임 산출물이라
# 재부팅·브랜치 전환으로 사라진다. 사라지면 2단계가 시작조차 못 하고,
# 값을 아는 사람이 손으로 다시 써 넣어야 한다. 여기 적어두면 저장소를
# checkout 하는 것만으로 복구된다.
#
# 출발 좌표는 여기 적지 않는다 — room_waypoints.yaml 에 이미 있고
# (bomi_map.sh 가 재매핑 때 갱신한다), 두 곳에 적으면 한쪽만 고쳐져
# 조용히 어긋난다. 아래는 "어느 웨이포인트를 출발점으로 볼지"만 정한다.

# 시연에 쓸 지도. src/mapping/maps/<이름>.yaml 이 있어야 한다.
MAP=bomi_real_15

# 출발 좌표로 쓸 웨이포인트 이름. charging 은 DEFAULT(대기 위치)이며
# bomi_map.sh 가 매핑 출발 지점으로 갱신한다.
FALLBACK_START_WAYPOINT=charging
