-- V3 : 현관 이벤트 원장(occupancy_event)
--
-- scenario 는 '인사 시나리오 실행'을 기록한다. 이 표는 '사실'을 기록한다. 둘은 다르다.
-- 인사를 안 했어도(TTL 만료, 게이트 차단) 문을 통과한 사실은 남아야 한다.
--
-- 무엇을 가능하게 하나
--   1. 루틴 베이스라인 학습 — "이 어르신이 평소 안 조용한 시간에 조용하다"를 판정하려면
--      평소의 리듬을 알아야 한다. 침묵 오탐을 걷어내는 1차 필터가 이것이다.
--   2. 외출 빈도 추세 — 발화량 말고 두 번째 활동 지표. 급감은 우울·건강 악화 신호(T2).
--   3. 야간 배회 감지 — 야간 외출은 치매의 대표 증상이고, 이것은 '침묵'이 아니라 '활동'이라
--      침묵 사다리로는 원리적으로 잡히지 않는다.
--
-- 하루에 몇 행 수준이다. 주기 측정값을 전부 적는 표가 아니다.
-- 참고: CLAUDE.md §11(현관 센서와 재실), §19
CREATE TABLE occupancy_event (
    id                  uuid          NOT NULL,
    senior_id           uuid          NOT NULL,
    robot_id            uuid,

    -- IN / OUT. NULL 을 허용하는 이유는 방향이 없는 재실 변화가 실재하기 때문이다.
    -- 하트비트가 끊겨 UNKNOWN 으로 강등되는 것도, 발화로 HOME 이 확정되는 것도
    -- 문을 통과한 사건이 아니다. source 를 보면 무엇이었는지 알 수 있다.
    direction           varchar(10),

    -- DOOR_SENSOR  현관 노드가 통과를 확정했다
    -- SPEECH       발화가 감지됐다. 발화는 센서를 이긴다(§11) — 말하고 있으면 집에 있다
    -- HEARTBEAT_TIMEOUT 현관 노드가 죽었다. 마지막 이벤트를 영원히 믿지 않는다
    source              varchar(30)   NOT NULL,

    -- 이 이벤트를 적용한 결과의 재실 상태. robot.occupancy_status 의 이력이기도 하다.
    -- 결과를 함께 적어두면 "그때 우리가 무엇으로 판단했는가"를 재구성할 수 있다.
    resulting_occupancy varchar(30)   NOT NULL,

    -- Jetson 이 이벤트를 받은 시각. '권위 있는' 시각이다.
    --
    -- 왜 Pi 의 시각을 권위로 쓰지 않는가
    --   배터리 백업 RTC 가 없는 라즈베리파이는 잘못된 시계로 부팅할 수 있다. 틀린 문
    --   타임스탬프는 루틴 베이스라인과 TTL 계산을 동시에 오염시킨다. 그래서 도착 시점에
    --   정규화하고(clock.now()), Pi 의 시각은 참고용으로만 남긴다.
    occurred_at         timestamptz   NOT NULL,
    reported_at         timestamptz,

    created_at          timestamptz   NOT NULL,
    CONSTRAINT pk_occupancy_event PRIMARY KEY (id)
);

-- 이 표는 시계열로 읽힌다. 베이스라인 학습과 외출 빈도 추세가 모두
-- "이 어르신의 최근 N일" 형태의 질의다. 추측이 아니라 확정된 사용 패턴이므로 인덱스를 둔다.
CREATE INDEX idx_occupancy_event_senior_occurred
    ON occupancy_event (senior_id, occurred_at);
