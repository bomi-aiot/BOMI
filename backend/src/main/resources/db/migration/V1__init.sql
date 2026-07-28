-- V1 : BOMI 초기 스키마 (현재 JPA 엔티티 기준)
--
-- 규약:
--  * 모든 PK는 애플리케이션 생성 UUID (GenerationType.UUID) → DB 기본값 없음.
--  * 연관관계는 raw UUID 논리 참조. 물리 FK는 두지 않음(엔티티 컨벤션과 일치).
--  * enum(@Enumerated STRING) → varchar, JSONB → jsonb, TEXT[] → varchar(255)[],
--    OffsetDateTime → timestamptz.
--  * embedding(VECTOR)/pgvector는 엔티티가 아직 매핑하지 않아 제외 → 후속 V2.
-- Hibernate ddl-auto=validate 로 엔티티↔스키마 정합을 검증한다.

-- 사용자 ------------------------------------------------------------------
CREATE TABLE app_user (
    id                              uuid          NOT NULL,
    user_type                       varchar(30)   NOT NULL,
    name                            varchar(100)  NOT NULL,
    email                           varchar(255),
    preferred_name                  varchar(100),
    conversation_preferences        jsonb         NOT NULL,
    onboarding_status               varchar(30)   NOT NULL,
    time_zone                       varchar(50)   NOT NULL,
    personalization_consent_status  varchar(30)   NOT NULL,
    health_data_consent_status      varchar(30)   NOT NULL,
    schedule_consent_status         varchar(30)   NOT NULL,
    guardian_sharing_consent_status varchar(30)   NOT NULL,
    status                          varchar(30)   NOT NULL,
    created_at                      timestamptz   NOT NULL,
    updated_at                      timestamptz   NOT NULL,
    CONSTRAINT pk_app_user PRIMARY KEY (id)
);

-- 로봇 --------------------------------------------------------------------
CREATE TABLE robot (
    id                      uuid          NOT NULL,
    senior_id               uuid,
    device_id               varchar(64),
    current_mode            varchar(30)   NOT NULL,
    ambient_temperature_c   numeric(5, 2),
    ambient_humidity_percent numeric(5, 2),
    ambient_observed_at     timestamptz,
    is_active               boolean       NOT NULL,
    CONSTRAINT pk_robot PRIMARY KEY (id),
    CONSTRAINT uq_robot_device_id UNIQUE (device_id)
);

-- 돌봄 관계 ----------------------------------------------------------------
CREATE TABLE care_relationship (
    id                                          uuid          NOT NULL,
    senior_id                                   uuid          NOT NULL,
    guardian_id                                 uuid          NOT NULL,
    priority                                    varchar(30)   NOT NULL,
    status                                      varchar(30)   NOT NULL,
    connected_at                                timestamptz   NOT NULL,
    care_management_permission_status           varchar(30)   NOT NULL,
    care_management_permission_updated_at       timestamptz,
    care_management_permission_granted_by_user_id uuid,
    CONSTRAINT pk_care_relationship PRIMARY KEY (id)
);

-- 온보딩 세션 --------------------------------------------------------------
CREATE TABLE onboarding_session (
    id                    uuid          NOT NULL,
    senior_id             uuid          NOT NULL,
    robot_id              uuid,
    question_set_version  varchar(50),
    started_channel       varchar(30)   NOT NULL,
    status                varchar(30)   NOT NULL,
    current_question_code varchar(100),
    started_at            timestamptz   NOT NULL,
    completed_at          timestamptz,
    ended_at              timestamptz,
    CONSTRAINT pk_onboarding_session PRIMARY KEY (id)
);

-- 온보딩 답변 --------------------------------------------------------------
CREATE TABLE onboarding_answer (
    id                    uuid          NOT NULL,
    session_id            uuid          NOT NULL,
    question_code         varchar(100)  NOT NULL,
    answer_value          jsonb,
    answered_channel      varchar(30)   NOT NULL,
    respondent_user_id    uuid,
    source_conversation_id uuid,
    source_message_id     uuid,
    verification_status   varchar(30)   NOT NULL,
    confirmed_by_user_id  uuid,
    answered_at           timestamptz,
    confirmed_at          timestamptz,
    updated_at            timestamptz,
    CONSTRAINT pk_onboarding_answer PRIMARY KEY (id)
);

-- 시나리오 ----------------------------------------------------------------
CREATE TABLE scenario (
    id                uuid          NOT NULL,
    senior_id         uuid          NOT NULL,
    robot_id          uuid          NOT NULL,
    external_event_id varchar(255),
    scenario_type     varchar(50)   NOT NULL,
    final_status      varchar(50)   NOT NULL,
    CONSTRAINT pk_scenario PRIMARY KEY (id)
);

-- 대화 --------------------------------------------------------------------
CREATE TABLE conversation (
    id                      uuid          NOT NULL,
    senior_id               uuid          NOT NULL,
    scenario_id             uuid,
    status                  varchar(30)   NOT NULL,
    started_at              timestamptz,
    ended_at                timestamptz,
    raw_messages_expires_at timestamptz,
    CONSTRAINT pk_conversation PRIMARY KEY (id)
);

-- 대화 메시지 --------------------------------------------------------------
CREATE TABLE conversation_message (
    id              uuid          NOT NULL,
    conversation_id uuid          NOT NULL,
    sequence_no     integer       NOT NULL,
    role            varchar(20)   NOT NULL,
    content         text          NOT NULL,
    occurred_at     timestamptz   NOT NULL,
    created_at      timestamptz   NOT NULL,
    CONSTRAINT pk_conversation_message PRIMARY KEY (id),
    CONSTRAINT uq_conversation_message_seq UNIQUE (conversation_id, sequence_no)
);

-- 대화 요약 ----------------------------------------------------------------
CREATE TABLE conversation_summary (
    id                   uuid          NOT NULL,
    senior_id            uuid          NOT NULL,
    conversation_id      uuid,
    summary_type         varchar(30)   NOT NULL,
    period_started_at    timestamptz   NOT NULL,
    period_ended_at      timestamptz   NOT NULL,
    content              text          NOT NULL,
    source_message_count integer       NOT NULL,
    generated_at         timestamptz   NOT NULL,
    superseded_by_id     uuid,
    CONSTRAINT pk_conversation_summary PRIMARY KEY (id),
    CONSTRAINT uq_conversation_summary_period
        UNIQUE (senior_id, summary_type, period_started_at, period_ended_at)
);

-- 사실 후보 ----------------------------------------------------------------
CREATE TABLE fact_candidate (
    id                        uuid          NOT NULL,
    senior_id                 uuid          NOT NULL,
    source_type               varchar(40)   NOT NULL,
    onboarding_answer_id      uuid,
    conversation_id           uuid,
    source_message_id         uuid,
    target_domain             varchar(40)   NOT NULL,
    fact_type                 varchar(80)   NOT NULL,
    operation                 varchar(20)   NOT NULL,
    target_entity_id          uuid,
    proposed_value            jsonb         NOT NULL,
    confirmed_value           jsonb,
    missing_fields            varchar(255)[] NOT NULL,
    risk_level                varchar(20)   NOT NULL,
    status                    varchar(40)   NOT NULL,
    clarification_reason      varchar(60),
    clarification_count       integer       NOT NULL,
    initiated_by_user_id      uuid,
    confirmed_by_user_id      uuid,
    requires_coordination     boolean       NOT NULL,
    coordination_status       varchar(50)   NOT NULL,
    senior_position           varchar(30)   NOT NULL,
    primary_guardian_decision varchar(50)   NOT NULL,
    primary_guardian_id       uuid,
    contact_attempt_count     integer       NOT NULL,
    last_contact_attempted_at timestamptz,
    unreachable_reason        varchar(50),
    coordination_deadline_at  timestamptz,
    coordination_completed_at timestamptz,
    coordination_note         text,
    materialized_target_id    uuid,
    materialized_at           timestamptz,
    created_at                timestamptz   NOT NULL,
    updated_at                timestamptz   NOT NULL,
    confirmed_at              timestamptz,
    expires_at                timestamptz,
    CONSTRAINT pk_fact_candidate PRIMARY KEY (id)
);

-- 장기 기억 ----------------------------------------------------------------
CREATE TABLE memory (
    id                    uuid          NOT NULL,
    senior_id             uuid          NOT NULL,
    source_conversation_id uuid,
    source_summary_id     uuid,
    source_candidate_id   uuid,
    superseded_by_id      uuid,
    memory_type           varchar(50)   NOT NULL,
    content               text          NOT NULL,
    verification_status   varchar(30)   NOT NULL,
    lifecycle_status      varchar(30)   NOT NULL,
    visibility            varchar(30)   NOT NULL,
    keywords              varchar(255)[],
    importance            smallint,
    first_observed_at     timestamptz,
    last_confirmed_at     timestamptz,
    last_used_at          timestamptz,
    CONSTRAINT pk_memory PRIMARY KEY (id),
    CONSTRAINT uq_memory_source_candidate UNIQUE (source_candidate_id)
);

-- 돌봄 기록 ----------------------------------------------------------------
CREATE TABLE care_record (
    id                    uuid          NOT NULL,
    senior_id             uuid          NOT NULL,
    parent_record_id      uuid,
    scenario_id           uuid,
    source_conversation_id uuid,
    source_message_id     uuid,
    recipient_guardian_id uuid,
    created_by_user_id    uuid,
    source_candidate_id   uuid,
    record_type           varchar(50)   NOT NULL,
    status                varchar(30)   NOT NULL,
    details               jsonb         NOT NULL,
    recurrence            jsonb,
    CONSTRAINT pk_care_record PRIMARY KEY (id),
    CONSTRAINT uq_care_record_source_candidate UNIQUE (source_candidate_id)
);
