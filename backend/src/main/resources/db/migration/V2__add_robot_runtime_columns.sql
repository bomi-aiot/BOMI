-- V2 : 로봇 런타임(능동 발화 게이트·침묵 사다리)이 읽어야 하는 컬럼 보강
--
-- 삭제·변경은 없다. 전부 컬럼 추가다. V1 은 이미 적용된 마이그레이션이므로 수정하지 않는다.
-- 참고: CLAUDE.md §7(게이트), §10(침묵 사다리), §11(현관·재실), §19(DB 작업 항목)

-- 사용자: quiet hours 와 거주 좌표 ------------------------------------------
--
-- quiet hours 는 능동 발화마다 게이트가 읽고, 침묵 사다리도 같은 값을 공유한다.
-- 새벽 4시의 침묵은 경고 신호가 아니라 수면이다.
--
-- 왜 conversation_preferences(jsonb) 가 아니라 별도 컬럼인가
--   매 능동 틱에서 읽고 시각 비교에 쓰는 값이다. jsonb 안에 두면 조회마다 추출·형변환이
--   붙고, 타입이 보장되지 않아 "22시"가 문자열로 들어가도 DB 가 막아주지 않는다.
--
-- 왜 NOT NULL DEFAULT 인가
--   NULL 은 "조용한 시간대가 없다" = 새벽 3시에도 떠들어도 된다는 뜻이 된다. 돌봄 기기에서
--   안전한 기본값은 '창이 있다'는 쪽이다. 값을 안 정한 어르신이 밤에 깨는 일이 없어야 한다.
--
-- 시간대 주의
--   time(로컬 시각)이며 UTC 가 아니다. 해석은 app_user.time_zone 으로 한다. 22:00~07:00 처럼
--   자정을 넘는 창이 정상이므로, start > end 인 경우를 반드시 처리해야 한다(naive 한 비교는
--   가장 중요한 시간대에서 틀린다).
ALTER TABLE app_user
    ADD COLUMN quiet_hours_start time NOT NULL DEFAULT '22:00',
    ADD COLUMN quiet_hours_end   time NOT NULL DEFAULT '07:00',
    -- 병원·약국 근처 조회의 기준점. 없으면 그 기능이 출처를 갖지 못한다.
    -- numeric(9,6) = 소수 6자리(약 0.1m 해상도)이고 위도(±90)·경도(±180)를 모두 담는다.
    -- NULL 허용: 좌표를 모르는 어르신도 있고, 그때는 위치 기능만 저하되면 된다.
    ADD COLUMN home_latitude     numeric(9, 6),
    ADD COLUMN home_longitude    numeric(9, 6);

-- 로봇: 재실 상태와 현관 노드 하트비트 ---------------------------------------
--
-- occupancy 는 침묵의 의미를 가르는 가장 값비싼 입력이다.
-- HOME+AWAKE+침묵은 의심스럽고, AWAY+침묵은 정상이다.
--
-- 왜 기본값이 HOME 이 아니라 UNKNOWN 인가
--   현관 노드로부터 아직 아무 소식도 못 들은 상태에서 HOME 이라고 가정하면, 어쩌면 빈 집을
--   상대로 침묵 사다리가 돌아가고 결국 보호자에게 오탐 알림이 간다. 보수적 추정이 UNKNOWN 이
--   존재하는 이유다.
ALTER TABLE robot
    ADD COLUMN occupancy_status       varchar(30) NOT NULL DEFAULT 'UNKNOWN',
    ADD COLUMN occupancy_observed_at  timestamptz,
    -- 현관 라즈베리파이의 마지막 하트비트 시각.
    --
    -- 이 컬럼이 없으면 "아무도 움직이지 않았다"와 "라즈베리파이가 죽었다"를 구분할 수 없다.
    -- 안전 시스템에서 그것은 조용한 실패다. 문 이벤트는 '일어난 일'만 알려주므로,
    -- 아무 일도 없는 상태의 정상 여부는 하트비트만이 답할 수 있다.
    -- NULL = 아직 한 번도 못 받음 → occupancy 를 UNKNOWN 으로 취급한다.
    ADD COLUMN door_node_heartbeat_at timestamptz;

-- 대화 메시지: 로봇이 왜 말했는가 --------------------------------------------
--
-- 세 가지 용도가 있다.
--   1. 사후 감사 — "왜 로봇이 새벽 3시에 말했는가"에 답할 수 있어야 한다.
--   2. T2 활동 지표 — 어르신 발화량과 로봇 발화량을 분리해야 한다. role 만으로는
--      로봇이 먼저 말을 건 것인지 대답한 것인지 알 수 없다.
--   3. 표현 다양화 — 같은 종류의 알림에서 최근에 쓴 문구를 조회해 반복을 피한다.
--
-- 왜 NULL 을 허용하는가
--   이 마이그레이션 이전에 쌓인 행들은 어떤 경로로 생겼는지 알 수 없다. 전부 'USER' 로
--   채우면 ROBOT 행까지 거짓으로 분류된다. 모르는 것은 NULL 로 두는 편이 정직하다.
--   대신 이후의 모든 쓰기는 반드시 값을 채운다.
ALTER TABLE conversation_message
    ADD COLUMN trigger_type varchar(30),
    -- 능동 발화만 우선순위를 갖는다. 어르신에게 대답하는 턴은 허락을 받을 필요가 없어서
    -- 게이트를 거치지 않으므로 우선순위가 없다.
    ADD COLUMN priority     varchar(20);

-- 돌봄 기록: 보호자 알림의 티어 ----------------------------------------------
--
-- T1 즉시(동의 불필요) / T2 일일 요약(통보) / T3 동의 필요.
-- recipient_guardian_id 는 이미 있으므로 "누구에게"는 해결돼 있고, "얼마나 급한가"가 없었다.
--
-- 왜 details(jsonb) 안이 아니라 컬럼인가
--   "아직 못 보낸 T1 이 있는가"는 안전 질의다. jsonb 안에 두면 인덱스 없이 매번 추출해야 한다.
--
-- T4 는 이 컬럼에 오지 않는다
--   T4 는 '절대 보내지 않음'이므로 알림 레코드 자체가 생기지 않는다. T4 는 알림의 티어가
--   아니라 기억의 공개범위(memory.visibility = PRIVATE, 시니어 전용)로 표현된다.
ALTER TABLE care_record
    ADD COLUMN notification_tier varchar(10);
