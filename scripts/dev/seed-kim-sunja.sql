-- 김순자 가구 개발용 seed 데이터
--
-- 대상: backend/src/main/resources/db/migration/V1__init.sql로 생성된 빈 bomi DB
-- 주의:
--   * Flyway migration이 아니다.
--   * 대상 13개 테이블(V10의 known_person 포함) 중 하나라도 비어 있지 않으면
--     아무 데이터도 넣지 않는다.
--   * 삭제/초기화/UPSERT를 수행하지 않는다.
--   * 모든 시각은 한 트랜잭션의 CURRENT_TIMESTAMP를 기준으로 계산한다.
--
-- S15P11E102-260: known_person 에 사망 가족 1명·생존 가족 1명을 추가했다. 완료
-- 조건이 "프롬프트의 '말하지 않을 주제' 섹션이 실제로 렌더링되는 것을 눈으로
-- 확인한다"를 요구하는데, 그 섹션은 known_person 이 최소 한 건 있어야만 채워지고
-- 지금까지는 이 데이터를 만드는 코드가 저장소 어디에도 없었다.

BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM app_user LIMIT 1)
       OR EXISTS (SELECT 1 FROM care_relationship LIMIT 1)
       OR EXISTS (SELECT 1 FROM robot LIMIT 1)
       OR EXISTS (SELECT 1 FROM onboarding_session LIMIT 1)
       OR EXISTS (SELECT 1 FROM onboarding_answer LIMIT 1)
       OR EXISTS (SELECT 1 FROM scenario LIMIT 1)
       OR EXISTS (SELECT 1 FROM conversation LIMIT 1)
       OR EXISTS (SELECT 1 FROM conversation_message LIMIT 1)
       OR EXISTS (SELECT 1 FROM conversation_summary LIMIT 1)
       OR EXISTS (SELECT 1 FROM fact_candidate LIMIT 1)
       OR EXISTS (SELECT 1 FROM memory LIMIT 1)
       OR EXISTS (SELECT 1 FROM care_record LIMIT 1)
       OR EXISTS (SELECT 1 FROM known_person LIMIT 1)
    THEN
        RAISE EXCEPTION
            '김순자 seed 중단: 대상 13개 테이블 중 비어 있지 않은 테이블이 있습니다.';
    END IF;
END
$$;

INSERT INTO app_user (
    id,
    user_type,
    name,
    email,
    preferred_name,
    conversation_preferences,
    onboarding_status,
    time_zone,
    personalization_consent_status,
    health_data_consent_status,
    schedule_consent_status,
    guardian_sharing_consent_status,
    status,
    created_at,
    updated_at
) VALUES
(
    '10000000-0000-4000-8000-000000000001',
    'SENIOR',
    '김순자',
    'kim.sunja@example.invalid',
    '순자님',
    '{"speechRate":"SLOW","volume":"LOUD","repeatWhenUnclear":true}'::jsonb,
    'COMPLETED',
    'Asia/Seoul',
    'GRANTED',
    'GRANTED',
    'GRANTED',
    'GRANTED',
    'ACTIVE',
    CURRENT_TIMESTAMP - INTERVAL '30 days',
    CURRENT_TIMESTAMP - INTERVAL '10 minutes'
),
(
    '10000000-0000-4000-8000-000000000002',
    'GUARDIAN',
    '우동균',
    'woo.donggyun@example.invalid',
    NULL,
    '{}'::jsonb,
    'NOT_STARTED',
    'Asia/Seoul',
    'NOT_ASKED',
    'NOT_ASKED',
    'NOT_ASKED',
    'NOT_ASKED',
    'ACTIVE',
    CURRENT_TIMESTAMP - INTERVAL '30 days',
    CURRENT_TIMESTAMP - INTERVAL '10 minutes'
),
(
    '10000000-0000-4000-8000-000000000003',
    'GUARDIAN',
    '차서영',
    'cha.seoyoung@example.invalid',
    NULL,
    '{}'::jsonb,
    'NOT_STARTED',
    'Asia/Seoul',
    'NOT_ASKED',
    'NOT_ASKED',
    'NOT_ASKED',
    'NOT_ASKED',
    'ACTIVE',
    CURRENT_TIMESTAMP - INTERVAL '30 days',
    CURRENT_TIMESTAMP - INTERVAL '10 minutes'
);

INSERT INTO care_relationship (
    id,
    senior_id,
    guardian_id,
    priority,
    status,
    connected_at,
    care_management_permission_status,
    care_management_permission_updated_at,
    care_management_permission_granted_by_user_id
) VALUES
(
    '11000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000002',
    'PRIMARY',
    'ACTIVE',
    CURRENT_TIMESTAMP - INTERVAL '20 days',
    'GRANTED',
    CURRENT_TIMESTAMP - INTERVAL '90 minutes',
    '10000000-0000-4000-8000-000000000001'
),
(
    '11000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000003',
    'SECONDARY',
    'ACTIVE',
    CURRENT_TIMESTAMP - INTERVAL '20 days',
    'NOT_ASKED',
    NULL,
    NULL
);

INSERT INTO robot (
    id,
    senior_id,
    device_id,
    current_mode,
    ambient_temperature_c,
    ambient_humidity_percent,
    ambient_observed_at,
    is_active
) VALUES (
    '20000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    'bomi-AA001',
    'IDLE',
    24.50,
    55.00,
    CURRENT_TIMESTAMP - INTERVAL '5 minutes',
    TRUE
);

INSERT INTO onboarding_session (
    id,
    senior_id,
    robot_id,
    question_set_version,
    started_channel,
    status,
    current_question_code,
    started_at,
    completed_at,
    ended_at
) VALUES (
    '30000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    '20000000-0000-4000-8000-000000000001',
    'onboarding-v1',
    'ROBOT',
    'COMPLETED',
    NULL,
    CURRENT_TIMESTAMP - INTERVAL '2 hours',
    CURRENT_TIMESTAMP - INTERVAL '90 minutes',
    CURRENT_TIMESTAMP - INTERVAL '90 minutes'
);

INSERT INTO onboarding_answer (
    id,
    session_id,
    question_code,
    answer_value,
    answered_channel,
    respondent_user_id,
    source_conversation_id,
    source_message_id,
    verification_status,
    confirmed_by_user_id,
    answered_at,
    confirmed_at,
    updated_at
) VALUES
(
    '31000000-0000-4000-8000-000000000001',
    '30000000-0000-4000-8000-000000000001',
    'PERSONALIZATION_CONSENT',
    '{"consentStatus":"GRANTED"}'::jsonb,
    'ROBOT',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'USER_CONFIRMED',
    '10000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '119 minutes',
    CURRENT_TIMESTAMP - INTERVAL '118 minutes',
    CURRENT_TIMESTAMP - INTERVAL '118 minutes'
),
(
    '31000000-0000-4000-8000-000000000002',
    '30000000-0000-4000-8000-000000000001',
    'HEALTH_DATA_CONSENT',
    '{"consentStatus":"GRANTED"}'::jsonb,
    'ROBOT',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'USER_CONFIRMED',
    '10000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '116 minutes',
    CURRENT_TIMESTAMP - INTERVAL '115 minutes',
    CURRENT_TIMESTAMP - INTERVAL '115 minutes'
),
(
    '31000000-0000-4000-8000-000000000003',
    '30000000-0000-4000-8000-000000000001',
    'SCHEDULE_CONSENT',
    '{"consentStatus":"GRANTED"}'::jsonb,
    'ROBOT',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'USER_CONFIRMED',
    '10000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '113 minutes',
    CURRENT_TIMESTAMP - INTERVAL '112 minutes',
    CURRENT_TIMESTAMP - INTERVAL '112 minutes'
),
(
    '31000000-0000-4000-8000-000000000004',
    '30000000-0000-4000-8000-000000000001',
    'GUARDIAN_SHARING_CONSENT',
    '{"consentStatus":"GRANTED"}'::jsonb,
    'ROBOT',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'USER_CONFIRMED',
    '10000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '110 minutes',
    CURRENT_TIMESTAMP - INTERVAL '109 minutes',
    CURRENT_TIMESTAMP - INTERVAL '109 minutes'
),
(
    '31000000-0000-4000-8000-000000000005',
    '30000000-0000-4000-8000-000000000001',
    'PREFERRED_NAME',
    '{"preferredName":"순자님"}'::jsonb,
    'ROBOT',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'USER_CONFIRMED',
    '10000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '106 minutes',
    CURRENT_TIMESTAMP - INTERVAL '105 minutes',
    CURRENT_TIMESTAMP - INTERVAL '105 minutes'
),
(
    '31000000-0000-4000-8000-000000000006',
    '30000000-0000-4000-8000-000000000001',
    'DAILY_ROUTINE',
    '{"content":"보통 아침 8시, 점심 12시, 저녁 6시에 식사한다.","keywords":["식사","생활 습관"]}'::jsonb,
    'ROBOT',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'USER_CONFIRMED',
    '10000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '102 minutes',
    CURRENT_TIMESTAMP - INTERVAL '101 minutes',
    CURRENT_TIMESTAMP - INTERVAL '101 minutes'
),
(
    '31000000-0000-4000-8000-000000000007',
    '30000000-0000-4000-8000-000000000001',
    'MEDICATION',
    '{"medicationName":"관절염약","dose":1,"doseUnit":"정"}'::jsonb,
    'ROBOT',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'USER_CONFIRMED',
    '10000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '98 minutes',
    CURRENT_TIMESTAMP - INTERVAL '97 minutes',
    CURRENT_TIMESTAMP - INTERVAL '97 minutes'
),
(
    '31000000-0000-4000-8000-000000000008',
    '30000000-0000-4000-8000-000000000001',
    'PRIMARY_GUARDIAN_CARE_MANAGEMENT_CONSENT',
    '{"guardianId":"10000000-0000-4000-8000-000000000002","consentStatus":"GRANTED"}'::jsonb,
    'ROBOT',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'USER_CONFIRMED',
    '10000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '94 minutes',
    CURRENT_TIMESTAMP - INTERVAL '93 minutes',
    CURRENT_TIMESTAMP - INTERVAL '93 minutes'
);

INSERT INTO scenario (
    id,
    senior_id,
    robot_id,
    external_event_id,
    scenario_type,
    final_status,
    -- V8: created_at/updated_at NOT NULL. 완료 시각을 과거로 두어
    -- ScenarioStartGuard 쿨다운(완료 후 30분)에 걸리지 않게 한다.
    created_at,
    updated_at
) VALUES (
    '40000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    '20000000-0000-4000-8000-000000000001',
    'seed-kim-sunja-manual-001',
    'MANUAL_INTERACTION',
    'COMPLETED',
    CURRENT_TIMESTAMP - INTERVAL '2 hours',
    CURRENT_TIMESTAMP - INTERVAL '2 hours'
);

INSERT INTO conversation (
    id,
    senior_id,
    scenario_id,
    status,
    started_at,
    ended_at,
    raw_messages_expires_at
) VALUES (
    '50000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    '40000000-0000-4000-8000-000000000001',
    'COMPLETED',
    CURRENT_TIMESTAMP - INTERVAL '30 minutes',
    CURRENT_TIMESTAMP - INTERVAL '20 minutes',
    CURRENT_TIMESTAMP + INTERVAL '30 days'
);

INSERT INTO conversation_message (
    id,
    conversation_id,
    sequence_no,
    role,
    content,
    occurred_at,
    created_at
) VALUES
(
    '51000000-0000-4000-8000-000000000001',
    '50000000-0000-4000-8000-000000000001',
    1,
    'ROBOT',
    '순자님, 현재 복용하고 계신 약이 있나요?',
    CURRENT_TIMESTAMP - INTERVAL '29 minutes',
    CURRENT_TIMESTAMP - INTERVAL '29 minutes'
),
(
    '51000000-0000-4000-8000-000000000002',
    '50000000-0000-4000-8000-000000000001',
    2,
    'SENIOR',
    '관절염약을 먹고 있어.',
    CURRENT_TIMESTAMP - INTERVAL '28 minutes',
    CURRENT_TIMESTAMP - INTERVAL '28 minutes'
),
(
    '51000000-0000-4000-8000-000000000003',
    '50000000-0000-4000-8000-000000000001',
    3,
    'ROBOT',
    '한 번에 얼마나 드시나요?',
    CURRENT_TIMESTAMP - INTERVAL '27 minutes',
    CURRENT_TIMESTAMP - INTERVAL '27 minutes'
),
(
    '51000000-0000-4000-8000-000000000004',
    '50000000-0000-4000-8000-000000000001',
    4,
    'SENIOR',
    '한 알씩 먹어.',
    CURRENT_TIMESTAMP - INTERVAL '26 minutes',
    CURRENT_TIMESTAMP - INTERVAL '26 minutes'
),
(
    '51000000-0000-4000-8000-000000000005',
    '50000000-0000-4000-8000-000000000001',
    5,
    'ROBOT',
    '언제 복용하시나요?',
    CURRENT_TIMESTAMP - INTERVAL '25 minutes',
    CURRENT_TIMESTAMP - INTERVAL '25 minutes'
),
(
    '51000000-0000-4000-8000-000000000006',
    '50000000-0000-4000-8000-000000000001',
    6,
    'SENIOR',
    '아침, 점심, 저녁을 먹고 30분 뒤에 먹어.',
    CURRENT_TIMESTAMP - INTERVAL '24 minutes',
    CURRENT_TIMESTAMP - INTERVAL '24 minutes'
),
(
    '51000000-0000-4000-8000-000000000007',
    '50000000-0000-4000-8000-000000000001',
    7,
    'ROBOT',
    '평소 식사 시간은 언제인가요?',
    CURRENT_TIMESTAMP - INTERVAL '23 minutes',
    CURRENT_TIMESTAMP - INTERVAL '23 minutes'
),
(
    '51000000-0000-4000-8000-000000000008',
    '50000000-0000-4000-8000-000000000001',
    8,
    'SENIOR',
    '아침 8시, 점심 12시, 저녁 6시쯤이야.',
    CURRENT_TIMESTAMP - INTERVAL '22 minutes',
    CURRENT_TIMESTAMP - INTERVAL '22 minutes'
),
(
    '51000000-0000-4000-8000-000000000009',
    '50000000-0000-4000-8000-000000000001',
    9,
    'ROBOT',
    '관절염약 한 정을 매일 8시 30분, 12시 30분, 18시 30분에 복용하는 것으로 저장할까요?',
    CURRENT_TIMESTAMP - INTERVAL '21 minutes',
    CURRENT_TIMESTAMP - INTERVAL '21 minutes'
),
(
    '51000000-0000-4000-8000-000000000010',
    '50000000-0000-4000-8000-000000000001',
    10,
    'SENIOR',
    '응, 그렇게 해.',
    CURRENT_TIMESTAMP - INTERVAL '20 minutes',
    CURRENT_TIMESTAMP - INTERVAL '20 minutes'
);

INSERT INTO conversation_summary (
    id,
    senior_id,
    conversation_id,
    summary_type,
    period_started_at,
    period_ended_at,
    content,
    source_message_count,
    generated_at,
    superseded_by_id
) VALUES (
    '52000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    '50000000-0000-4000-8000-000000000001',
    'CONVERSATION',
    CURRENT_TIMESTAMP - INTERVAL '30 minutes',
    CURRENT_TIMESTAMP - INTERVAL '20 minutes',
    '김순자는 관절염약을 한 번에 1정씩 매일 세 끼 식후 30분에 복용한다. 평소 식사 시각은 08:00, 12:00, 18:00이다.',
    10,
    CURRENT_TIMESTAMP - INTERVAL '19 minutes',
    NULL
);

INSERT INTO fact_candidate (
    id,
    senior_id,
    source_type,
    onboarding_answer_id,
    conversation_id,
    source_message_id,
    target_domain,
    fact_type,
    operation,
    target_entity_id,
    proposed_value,
    confirmed_value,
    missing_fields,
    risk_level,
    status,
    clarification_reason,
    clarification_count,
    initiated_by_user_id,
    confirmed_by_user_id,
    requires_coordination,
    coordination_status,
    senior_position,
    primary_guardian_decision,
    primary_guardian_id,
    contact_attempt_count,
    last_contact_attempted_at,
    unreachable_reason,
    coordination_deadline_at,
    coordination_completed_at,
    coordination_note,
    materialized_target_id,
    materialized_at,
    created_at,
    updated_at,
    confirmed_at,
    expires_at
) VALUES
(
    '60000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    'ONBOARDING_ANSWER',
    '31000000-0000-4000-8000-000000000007',
    NULL,
    NULL,
    'CARE_RECORD',
    'MEDICATION',
    'CREATE',
    NULL,
    '{"medicationName":"관절염약","dose":1,"doseUnit":"정"}'::jsonb,
    '{"medicationName":"관절염약","dose":1,"doseUnit":"정"}'::jsonb,
    ARRAY[]::varchar(255)[],
    'SENSITIVE',
    'MATERIALIZED',
    NULL,
    0,
    '10000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    FALSE,
    'NOT_REQUIRED',
    'AGREED',
    'PENDING',
    NULL,
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '80000000-0000-4000-8000-000000000001',
    CURRENT_TIMESTAMP - INTERVAL '95 minutes',
    CURRENT_TIMESTAMP - INTERVAL '98 minutes',
    CURRENT_TIMESTAMP - INTERVAL '95 minutes',
    CURRENT_TIMESTAMP - INTERVAL '96 minutes',
    NULL
),
(
    '60000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    'CONVERSATION_MESSAGE',
    NULL,
    '50000000-0000-4000-8000-000000000001',
    '51000000-0000-4000-8000-000000000010',
    'CARE_RECORD',
    'MEDICATION_SCHEDULE',
    'CREATE',
    NULL,
    '{"medicationName":"관절염약","mealTimes":["08:00","12:00","18:00"],"localTimes":["08:30","12:30","18:30"],"timeZone":"Asia/Seoul","instruction":"매 끼니 식후 30분"}'::jsonb,
    '{"medicationName":"관절염약","mealTimes":["08:00","12:00","18:00"],"localTimes":["08:30","12:30","18:30"],"timeZone":"Asia/Seoul","instruction":"매 끼니 식후 30분"}'::jsonb,
    ARRAY[]::varchar(255)[],
    'SENSITIVE',
    'MATERIALIZED',
    NULL,
    0,
    '10000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    FALSE,
    'NOT_REQUIRED',
    'AGREED',
    'PENDING',
    NULL,
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '80000000-0000-4000-8000-000000000002',
    CURRENT_TIMESTAMP - INTERVAL '18 minutes',
    CURRENT_TIMESTAMP - INTERVAL '19 minutes',
    CURRENT_TIMESTAMP - INTERVAL '18 minutes',
    CURRENT_TIMESTAMP - INTERVAL '18 minutes',
    NULL
);

INSERT INTO memory (
    id,
    senior_id,
    source_conversation_id,
    source_summary_id,
    source_candidate_id,
    superseded_by_id,
    memory_type,
    content,
    verification_status,
    lifecycle_status,
    visibility,
    keywords,
    importance,
    first_observed_at,
    last_confirmed_at,
    last_used_at
) VALUES
(
    '70000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    '50000000-0000-4000-8000-000000000001',
    '52000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'PREFERENCE',
    '김순자는 로봇이 천천히 크고 명확하게 말하는 것을 선호한다.',
    'USER_CONFIRMED',
    'ACTIVE',
    'PRIVATE',
    ARRAY['천천히', '명확하게', '대화 선호']::varchar(255)[],
    3,
    CURRENT_TIMESTAMP - INTERVAL '29 minutes',
    CURRENT_TIMESTAMP - INTERVAL '20 minutes',
    NULL
),
(
    '70000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    '50000000-0000-4000-8000-000000000001',
    '52000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    'DAILY_ROUTINE',
    '김순자는 보통 08:00, 12:00, 18:00에 식사한다.',
    'USER_CONFIRMED',
    'ACTIVE',
    'SHARED_WITH_PRIMARY',
    ARRAY['식사', '08:00', '12:00', '18:00']::varchar(255)[],
    4,
    CURRENT_TIMESTAMP - INTERVAL '102 minutes',
    CURRENT_TIMESTAMP - INTERVAL '20 minutes',
    NULL
);

INSERT INTO care_record (
    id,
    senior_id,
    parent_record_id,
    scenario_id,
    source_conversation_id,
    source_message_id,
    recipient_guardian_id,
    created_by_user_id,
    source_candidate_id,
    record_type,
    status,
    details,
    recurrence
) VALUES
(
    '80000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    NULL,
    NULL,
    NULL,
    '10000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    '60000000-0000-4000-8000-000000000001',
    'MEDICATION',
    'ACTIVE',
    '{"medicationName":"관절염약","dose":1,"doseUnit":"정","instruction":"매 끼니 식후 30분","sourceType":"ONBOARDING_ANSWER","verificationStatus":"USER_CONFIRMED"}'::jsonb,
    NULL
),
(
    '80000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    NULL,
    '40000000-0000-4000-8000-000000000001',
    '50000000-0000-4000-8000-000000000001',
    '51000000-0000-4000-8000-000000000010',
    '10000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    '60000000-0000-4000-8000-000000000002',
    'MEDICATION_SCHEDULE',
    'ACTIVE',
    '{"medicationName":"관절염약","mealTimes":["08:00","12:00","18:00"],"localTimes":["08:30","12:30","18:30"],"timeZone":"Asia/Seoul","instruction":"매 끼니 식후 30분","sourceType":"CONVERSATION_MESSAGE","verificationStatus":"USER_CONFIRMED"}'::jsonb,
    '{"frequency":"DAILY","times":["08:30","12:30","18:30"]}'::jsonb
);

-- S15P11E102-260: known_person — 사망 가족 1명 + 생존 가족 1명.
--
-- 사망: 남편 박정호. is_deceased = TRUE 이므로 문맥 조립 API 는 이 사람을 회피
-- 대상으로 판정하고, avoidTopics 에는 deceased_note 의 "1년 전 지병으로 별세"가
-- 아니라 금지문("박정호 이야기는 로봇이 먼저 꺼내지 않습니다")만 실린다
-- (ConversationContextService.avoidPhrase 참고, CLAUDE.md §8).
--
-- 생존: 아들 김민수. is_deceased = FALSE 이므로 회피 대상이 아니다 — 이 사람은
-- 오히려 "민수는 잘 있대요?" 같은 자연스러운 이어짐에 쓰일 수 있는 쪽이다.
INSERT INTO known_person (
    id,
    senior_id,
    guardian_user_id,
    display_name,
    relationship,
    is_deceased,
    deceased_note,
    lives_with,
    contact_frequency,
    last_mentioned_at,
    created_at,
    updated_at
) VALUES
(
    '90000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000002',
    '박정호',
    '배우자',
    TRUE,
    '1년 전 지병으로 별세',
    NULL,
    NULL,
    NULL,
    CURRENT_TIMESTAMP - INTERVAL '30 days',
    CURRENT_TIMESTAMP - INTERVAL '30 days'
),
(
    '90000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000002',
    '김민수',
    '아들',
    FALSE,
    NULL,
    FALSE,
    '주 1회',
    NULL,
    CURRENT_TIMESTAMP - INTERVAL '30 days',
    CURRENT_TIMESTAMP - INTERVAL '30 days'
);

COMMIT;

-- 실행 후 요약 확인
SELECT 'app_user' AS table_name, COUNT(*) AS row_count FROM app_user
UNION ALL SELECT 'care_relationship', COUNT(*) FROM care_relationship
UNION ALL SELECT 'robot', COUNT(*) FROM robot
UNION ALL SELECT 'onboarding_session', COUNT(*) FROM onboarding_session
UNION ALL SELECT 'onboarding_answer', COUNT(*) FROM onboarding_answer
UNION ALL SELECT 'scenario', COUNT(*) FROM scenario
UNION ALL SELECT 'conversation', COUNT(*) FROM conversation
UNION ALL SELECT 'conversation_message', COUNT(*) FROM conversation_message
UNION ALL SELECT 'conversation_summary', COUNT(*) FROM conversation_summary
UNION ALL SELECT 'fact_candidate', COUNT(*) FROM fact_candidate
UNION ALL SELECT 'memory', COUNT(*) FROM memory
UNION ALL SELECT 'care_record', COUNT(*) FROM care_record
UNION ALL SELECT 'known_person', COUNT(*) FROM known_person
ORDER BY table_name;
