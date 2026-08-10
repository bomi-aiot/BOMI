-- ============================================================
-- BOMI DB 덤프
--   생성 시각   : 2026-08-10T10:00:56+09:00
--   기준 커밋   : 1cd6f96911a5
--   PostgreSQL  : 17.10 (Debian 17.10-1.pgdg12+1)
--   pgvector    : (미설치)
--   Flyway 최종 : 18
--
-- 복원 전제: 대상 서버에 pgvector 확장이 설치되어 있어야 합니다.
--            (pgvector/pgvector:0.8.5-pg17 이미지 사용 시 충족)
-- 복원 예시:
--   createdb -U bomi bomi
--   psql -U bomi -d bomi -v ON_ERROR_STOP=1 -f bomi-dump-20260810-1000.sql
--
-- 주의: 이 파일에는 API 키·비밀번호가 들어 있지 않습니다.
--       모든 시크릿은 production.env 와 각 장치의 .env 에만 존재합니다.
-- ============================================================

--
-- PostgreSQL database dump
--

\restrict 38chcAVXyM98km4smRFhHF6d0q1D5OzopbYSsXMFhgM4HeBaieNxMZCfjnQqaji

-- Dumped from database version 17.10 (Debian 17.10-1.pgdg12+1)
-- Dumped by pg_dump version 17.10 (Debian 17.10-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

DROP INDEX IF EXISTS "public"."uq_scenario_wake_word_event";
DROP INDEX IF EXISTS "public"."uq_scenario_one_active_per_senior";
DROP INDEX IF EXISTS "public"."uq_fact_candidate_senior_message_fact_type";
DROP INDEX IF EXISTS "public"."ix_scenario_senior_type_status_updated";
DROP INDEX IF EXISTS "public"."ix_scenario_senior_status";
DROP INDEX IF EXISTS "public"."ix_scenario_active_walk_robot";
DROP INDEX IF EXISTS "public"."ix_robot_mode_recovery_audit_robot_time";
DROP INDEX IF EXISTS "public"."ix_conversation_pending_ai_start";
DROP INDEX IF EXISTS "public"."ix_conversation_active_ai";
DROP INDEX IF EXISTS "public"."ix_care_record_senior_type_occurred";
DROP INDEX IF EXISTS "public"."idx_occupancy_event_senior_occurred";
DROP INDEX IF EXISTS "public"."idx_memory_embedding_resync";
DROP INDEX IF EXISTS "public"."idx_known_person_senior";
DROP INDEX IF EXISTS "public"."idx_conversation_summary_embedding_resync";
DROP INDEX IF EXISTS "public"."flyway_schema_history_s_idx";
ALTER TABLE IF EXISTS ONLY "public"."walk_request_receipt" DROP CONSTRAINT IF EXISTS "walk_request_receipt_pkey";
ALTER TABLE IF EXISTS ONLY "public"."wake_word_trigger_receipt" DROP CONSTRAINT IF EXISTS "wake_word_trigger_receipt_pkey";
ALTER TABLE IF EXISTS ONLY "public"."walk_request_receipt" DROP CONSTRAINT IF EXISTS "uq_walk_request_ingress_request";
ALTER TABLE IF EXISTS ONLY "public"."scenario" DROP CONSTRAINT IF EXISTS "uq_scenario_active_navigation_command";
ALTER TABLE IF EXISTS ONLY "public"."robot" DROP CONSTRAINT IF EXISTS "uq_robot_device_id";
ALTER TABLE IF EXISTS ONLY "public"."memory" DROP CONSTRAINT IF EXISTS "uq_memory_source_candidate";
ALTER TABLE IF EXISTS ONLY "public"."daily_activity_metric" DROP CONSTRAINT IF EXISTS "uq_daily_activity_metric_day";
ALTER TABLE IF EXISTS ONLY "public"."conversation_summary" DROP CONSTRAINT IF EXISTS "uq_conversation_summary_period";
ALTER TABLE IF EXISTS ONLY "public"."conversation" DROP CONSTRAINT IF EXISTS "uq_conversation_start_command";
ALTER TABLE IF EXISTS ONLY "public"."conversation" DROP CONSTRAINT IF EXISTS "uq_conversation_scenario";
ALTER TABLE IF EXISTS ONLY "public"."conversation_message" DROP CONSTRAINT IF EXISTS "uq_conversation_message_seq";
ALTER TABLE IF EXISTS ONLY "public"."care_record" DROP CONSTRAINT IF EXISTS "uq_care_record_source_candidate";
ALTER TABLE IF EXISTS ONLY "public"."robot_mode_recovery_audit" DROP CONSTRAINT IF EXISTS "robot_mode_recovery_audit_pkey";
ALTER TABLE IF EXISTS ONLY "public"."scenario" DROP CONSTRAINT IF EXISTS "pk_scenario";
ALTER TABLE IF EXISTS ONLY "public"."robot" DROP CONSTRAINT IF EXISTS "pk_robot";
ALTER TABLE IF EXISTS ONLY "public"."onboarding_session" DROP CONSTRAINT IF EXISTS "pk_onboarding_session";
ALTER TABLE IF EXISTS ONLY "public"."onboarding_answer" DROP CONSTRAINT IF EXISTS "pk_onboarding_answer";
ALTER TABLE IF EXISTS ONLY "public"."occupancy_event" DROP CONSTRAINT IF EXISTS "pk_occupancy_event";
ALTER TABLE IF EXISTS ONLY "public"."memory" DROP CONSTRAINT IF EXISTS "pk_memory";
ALTER TABLE IF EXISTS ONLY "public"."known_person" DROP CONSTRAINT IF EXISTS "pk_known_person";
ALTER TABLE IF EXISTS ONLY "public"."fact_candidate" DROP CONSTRAINT IF EXISTS "pk_fact_candidate";
ALTER TABLE IF EXISTS ONLY "public"."daily_activity_metric" DROP CONSTRAINT IF EXISTS "pk_daily_activity_metric";
ALTER TABLE IF EXISTS ONLY "public"."conversation_summary" DROP CONSTRAINT IF EXISTS "pk_conversation_summary";
ALTER TABLE IF EXISTS ONLY "public"."conversation_message" DROP CONSTRAINT IF EXISTS "pk_conversation_message";
ALTER TABLE IF EXISTS ONLY "public"."conversation" DROP CONSTRAINT IF EXISTS "pk_conversation";
ALTER TABLE IF EXISTS ONLY "public"."care_relationship" DROP CONSTRAINT IF EXISTS "pk_care_relationship";
ALTER TABLE IF EXISTS ONLY "public"."care_record" DROP CONSTRAINT IF EXISTS "pk_care_record";
ALTER TABLE IF EXISTS ONLY "public"."app_user" DROP CONSTRAINT IF EXISTS "pk_app_user";
ALTER TABLE IF EXISTS ONLY "public"."flyway_schema_history" DROP CONSTRAINT IF EXISTS "flyway_schema_history_pk";
DROP TABLE IF EXISTS "public"."walk_request_receipt";
DROP TABLE IF EXISTS "public"."wake_word_trigger_receipt";
DROP TABLE IF EXISTS "public"."scenario";
DROP TABLE IF EXISTS "public"."robot_mode_recovery_audit";
DROP TABLE IF EXISTS "public"."robot";
DROP TABLE IF EXISTS "public"."onboarding_session";
DROP TABLE IF EXISTS "public"."onboarding_answer";
DROP TABLE IF EXISTS "public"."occupancy_event";
DROP TABLE IF EXISTS "public"."memory";
DROP TABLE IF EXISTS "public"."known_person";
DROP TABLE IF EXISTS "public"."flyway_schema_history";
DROP TABLE IF EXISTS "public"."fact_candidate";
DROP TABLE IF EXISTS "public"."daily_activity_metric";
DROP TABLE IF EXISTS "public"."conversation_summary";
DROP TABLE IF EXISTS "public"."conversation_message";
DROP TABLE IF EXISTS "public"."conversation";
DROP TABLE IF EXISTS "public"."care_relationship";
DROP TABLE IF EXISTS "public"."care_record";
DROP TABLE IF EXISTS "public"."app_user";
--
-- Name: SCHEMA "public"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA "public" IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = "heap";

--
-- Name: app_user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."app_user" (
    "id" "uuid" NOT NULL,
    "user_type" character varying(30) NOT NULL,
    "name" character varying(100) NOT NULL,
    "email" character varying(255),
    "preferred_name" character varying(100),
    "conversation_preferences" "jsonb" NOT NULL,
    "onboarding_status" character varying(30) NOT NULL,
    "time_zone" character varying(50) NOT NULL,
    "personalization_consent_status" character varying(30) NOT NULL,
    "health_data_consent_status" character varying(30) NOT NULL,
    "schedule_consent_status" character varying(30) NOT NULL,
    "guardian_sharing_consent_status" character varying(30) NOT NULL,
    "status" character varying(30) NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "quiet_hours_start" time without time zone DEFAULT '22:00:00'::time without time zone NOT NULL,
    "quiet_hours_end" time without time zone DEFAULT '07:00:00'::time without time zone NOT NULL,
    "home_latitude" numeric(9,6),
    "home_longitude" numeric(9,6),
    "birth_date" "date",
    "wake_time" time without time zone,
    "sleep_time" time without time zone,
    "chronic_pain_area" "text",
    "preferred_hospital" "text",
    "home_address" "text"
);


--
-- Name: COLUMN "app_user"."wake_time"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."app_user"."wake_time" IS '어르신의 평소 기상 시각(로컬, time_zone 기준). 침묵 사다리의 루틴 베이스라인이 읽을 값이며, 이 마이그레이션은 컬럼만 채운다 — 베이스라인 필터 자체는 S15P11E102-261 범위 밖이다(jobs/ticks.py 참고).';


--
-- Name: COLUMN "app_user"."sleep_time"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."app_user"."sleep_time" IS '어르신의 평소 취침 시각(로컬, time_zone 기준). wake_time 과 용도가 같다.';


--
-- Name: COLUMN "app_user"."chronic_pain_area"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."app_user"."chronic_pain_area" IS '어르신이 밝힌 만성 통증 부위(자유 문자열). 응급 판정에는 쓰지 않는다.';


--
-- Name: COLUMN "app_user"."preferred_hospital"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."app_user"."preferred_hospital" IS '어르신이 다니는 단골 병원·약국 이름(자유 문자열).';


--
-- Name: COLUMN "app_user"."home_address"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."app_user"."home_address" IS '어르신 자택 주소(자유 문자열, 시·군·구 수준 권장). 날씨 기본 지역 등 대화 문맥의 기본값으로 쓴다. 지오 검색용 좌표(home_latitude/longitude)와 별개이며, 모르면 null이다.';


--
-- Name: care_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."care_record" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "parent_record_id" "uuid",
    "scenario_id" "uuid",
    "source_conversation_id" "uuid",
    "source_message_id" "uuid",
    "recipient_guardian_id" "uuid",
    "created_by_user_id" "uuid",
    "source_candidate_id" "uuid",
    "record_type" character varying(50) NOT NULL,
    "status" character varying(30) NOT NULL,
    "details" "jsonb" NOT NULL,
    "recurrence" "jsonb",
    "notification_tier" character varying(10),
    "occurred_at" timestamp with time zone
);


--
-- Name: COLUMN "care_record"."occurred_at"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."care_record"."occurred_at" IS '이 기록이 시간축 위에 놓이는 지점. 일어난 일이면 일어난 시각, 예정된 일이면 예정 시각. NULL 은 "모른다" 또는 "시점이 없다(반복 규칙, 처방 자체)"를 뜻한다. S15P11E102-230';


--
-- Name: care_relationship; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."care_relationship" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "guardian_id" "uuid" NOT NULL,
    "priority" character varying(30) NOT NULL,
    "status" character varying(30) NOT NULL,
    "connected_at" timestamp with time zone NOT NULL,
    "care_management_permission_status" character varying(30) NOT NULL,
    "care_management_permission_updated_at" timestamp with time zone,
    "care_management_permission_granted_by_user_id" "uuid"
);


--
-- Name: conversation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."conversation" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "scenario_id" "uuid",
    "status" character varying(30) NOT NULL,
    "started_at" timestamp with time zone,
    "ended_at" timestamp with time zone,
    "raw_messages_expires_at" timestamp with time zone,
    "sealed" boolean DEFAULT false NOT NULL,
    "start_command_id" character varying(64),
    "ai_started_at" timestamp with time zone,
    "end_outcome" character varying(30),
    "reason_code" character varying(100)
);


--
-- Name: COLUMN "conversation"."started_at"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."conversation"."started_at" IS '일반 대화 시작 시각 또는 시나리오 START_CONVERSATION 요청 시각';


--
-- Name: COLUMN "conversation"."sealed"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."conversation"."sealed" IS '이 대화가 "우리끼리 얘기"로 봉인됐는가. 봉인된 대화는 요약 생성(외부 생성형 LLM 호출) 대상에서 제외한다(CLAUDE.md §9 T4). 한 방향 플래그 — 해제 없음.';


--
-- Name: COLUMN "conversation"."ai_started_at"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."conversation"."ai_started_at" IS 'AI가 CONVERSATION_STARTED로 수락을 확인한 시각';


--
-- Name: conversation_message; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."conversation_message" (
    "id" "uuid" NOT NULL,
    "conversation_id" "uuid" NOT NULL,
    "sequence_no" integer NOT NULL,
    "role" character varying(20) NOT NULL,
    "content" "text" NOT NULL,
    "occurred_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "trigger_type" character varying(30),
    "priority" character varying(20),
    "orientation_question" boolean
);


--
-- Name: conversation_summary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."conversation_summary" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "conversation_id" "uuid",
    "summary_type" character varying(30) NOT NULL,
    "period_started_at" timestamp with time zone NOT NULL,
    "period_ended_at" timestamp with time zone NOT NULL,
    "content" "text" NOT NULL,
    "source_message_count" integer NOT NULL,
    "generated_at" timestamp with time zone NOT NULL,
    "superseded_by_id" "uuid",
    "embedding_status" character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    "embedding_synced_at" timestamp with time zone,
    "embedding_model" character varying(100)
);


--
-- Name: daily_activity_metric; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."daily_activity_metric" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "metric_date" "date" NOT NULL,
    "medication_taken_count" smallint,
    "medication_scheduled_count" smallint,
    "meal_count" smallint,
    "water_intake_count" smallint,
    "sleep_minutes" integer,
    "mood_score" smallint,
    "senior_utterance_count" integer,
    "robot_utterance_count" integer,
    "outing_count" smallint,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "orientation_question_repeat_count" smallint,
    "summary_sent_at" timestamp with time zone
);


--
-- Name: fact_candidate; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."fact_candidate" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "source_type" character varying(40) NOT NULL,
    "onboarding_answer_id" "uuid",
    "conversation_id" "uuid",
    "source_message_id" "uuid",
    "target_domain" character varying(40) NOT NULL,
    "fact_type" character varying(80) NOT NULL,
    "operation" character varying(20) NOT NULL,
    "target_entity_id" "uuid",
    "proposed_value" "jsonb" NOT NULL,
    "confirmed_value" "jsonb",
    "missing_fields" character varying(255)[] NOT NULL,
    "risk_level" character varying(20) NOT NULL,
    "status" character varying(40) NOT NULL,
    "clarification_reason" character varying(60),
    "clarification_count" integer NOT NULL,
    "initiated_by_user_id" "uuid",
    "confirmed_by_user_id" "uuid",
    "requires_coordination" boolean NOT NULL,
    "coordination_status" character varying(50) NOT NULL,
    "senior_position" character varying(30) NOT NULL,
    "primary_guardian_decision" character varying(50) NOT NULL,
    "primary_guardian_id" "uuid",
    "contact_attempt_count" integer NOT NULL,
    "last_contact_attempted_at" timestamp with time zone,
    "unreachable_reason" character varying(50),
    "coordination_deadline_at" timestamp with time zone,
    "coordination_completed_at" timestamp with time zone,
    "coordination_note" "text",
    "materialized_target_id" "uuid",
    "materialized_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "confirmed_at" timestamp with time zone,
    "expires_at" timestamp with time zone
);


--
-- Name: flyway_schema_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."flyway_schema_history" (
    "installed_rank" integer NOT NULL,
    "version" character varying(50),
    "description" character varying(200) NOT NULL,
    "type" character varying(20) NOT NULL,
    "script" character varying(1000) NOT NULL,
    "checksum" integer,
    "installed_by" character varying(100) NOT NULL,
    "installed_on" timestamp without time zone DEFAULT "now"() NOT NULL,
    "execution_time" integer NOT NULL,
    "success" boolean NOT NULL
);


--
-- Name: known_person; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."known_person" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "guardian_user_id" "uuid",
    "display_name" character varying(100) NOT NULL,
    "relationship" character varying(50),
    "is_deceased" boolean,
    "deceased_note" character varying(500),
    "lives_with" boolean,
    "contact_frequency" character varying(50),
    "last_mentioned_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL
);


--
-- Name: memory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."memory" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "source_conversation_id" "uuid",
    "source_summary_id" "uuid",
    "source_candidate_id" "uuid",
    "superseded_by_id" "uuid",
    "memory_type" character varying(50) NOT NULL,
    "content" "text" NOT NULL,
    "verification_status" character varying(30) NOT NULL,
    "lifecycle_status" character varying(30) NOT NULL,
    "visibility" character varying(30) NOT NULL,
    "keywords" character varying(255)[],
    "importance" smallint,
    "first_observed_at" timestamp with time zone,
    "last_confirmed_at" timestamp with time zone,
    "last_used_at" timestamp with time zone,
    "embedding_status" character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    "embedding_synced_at" timestamp with time zone,
    "embedding_model" character varying(100)
);


--
-- Name: occupancy_event; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."occupancy_event" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "robot_id" "uuid",
    "direction" character varying(10),
    "source" character varying(30) NOT NULL,
    "resulting_occupancy" character varying(30) NOT NULL,
    "occurred_at" timestamp with time zone NOT NULL,
    "reported_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL
);


--
-- Name: onboarding_answer; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."onboarding_answer" (
    "id" "uuid" NOT NULL,
    "session_id" "uuid" NOT NULL,
    "question_code" character varying(100) NOT NULL,
    "answer_value" "jsonb",
    "answered_channel" character varying(30) NOT NULL,
    "respondent_user_id" "uuid",
    "source_conversation_id" "uuid",
    "source_message_id" "uuid",
    "verification_status" character varying(30) NOT NULL,
    "confirmed_by_user_id" "uuid",
    "answered_at" timestamp with time zone,
    "confirmed_at" timestamp with time zone,
    "updated_at" timestamp with time zone
);


--
-- Name: onboarding_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."onboarding_session" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "robot_id" "uuid",
    "question_set_version" character varying(50),
    "started_channel" character varying(30) NOT NULL,
    "status" character varying(30) NOT NULL,
    "current_question_code" character varying(100),
    "started_at" timestamp with time zone NOT NULL,
    "completed_at" timestamp with time zone,
    "ended_at" timestamp with time zone
);


--
-- Name: robot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."robot" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid",
    "device_id" character varying(64),
    "current_mode" character varying(30) NOT NULL,
    "ambient_temperature_c" numeric(5,2),
    "ambient_humidity_percent" numeric(5,2),
    "ambient_observed_at" timestamp with time zone,
    "is_active" boolean NOT NULL,
    "occupancy_status" character varying(30) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    "occupancy_observed_at" timestamp with time zone,
    "door_node_heartbeat_at" timestamp with time zone
);


--
-- Name: robot_mode_recovery_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."robot_mode_recovery_audit" (
    "id" "uuid" NOT NULL,
    "robot_id" "uuid" NOT NULL,
    "robot_device_id" character varying(64) NOT NULL,
    "operator_id" character varying(100) NOT NULL,
    "previous_mode" character varying(30) NOT NULL,
    "target_mode" character varying(30) NOT NULL,
    "disposition" character varying(30) NOT NULL,
    "physical_safety_confirmed" boolean NOT NULL,
    "reason" character varying(500) NOT NULL,
    "recovered_at" timestamp with time zone NOT NULL,
    CONSTRAINT "ck_robot_mode_recovery_device_id" CHECK ((("length"("btrim"(("robot_device_id")::"text")) >= 1) AND ("length"("btrim"(("robot_device_id")::"text")) <= 64))),
    CONSTRAINT "ck_robot_mode_recovery_disposition" CHECK ((((("disposition")::"text" = 'RECOVERED'::"text") AND (("previous_mode")::"text" = ANY ((ARRAY['SAFE_STOP'::character varying, 'SCENARIO_ACTIVE'::character varying])::"text"[]))) OR ((("disposition")::"text" = 'NO_OP_ALREADY_IDLE'::"text") AND (("previous_mode")::"text" = 'IDLE'::"text")))),
    CONSTRAINT "ck_robot_mode_recovery_operator_id" CHECK ((("length"("btrim"(("operator_id")::"text")) >= 1) AND ("length"("btrim"(("operator_id")::"text")) <= 100))),
    CONSTRAINT "ck_robot_mode_recovery_physical_confirmation" CHECK ("physical_safety_confirmed"),
    CONSTRAINT "ck_robot_mode_recovery_reason" CHECK ((("length"("btrim"(("reason")::"text")) >= 1) AND ("length"("btrim"(("reason")::"text")) <= 500))),
    CONSTRAINT "ck_robot_mode_recovery_target_idle" CHECK ((("target_mode")::"text" = 'IDLE'::"text"))
);


--
-- Name: TABLE "robot_mode_recovery_audit"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE "public"."robot_mode_recovery_audit" IS 'Authenticated operator audit for DB mode recovery to IDLE; never a physical safety action.';


--
-- Name: COLUMN "robot_mode_recovery_audit"."operator_id"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."robot_mode_recovery_audit"."operator_id" IS 'Server-configured authenticated operator identity, never supplied in the request body.';


--
-- Name: COLUMN "robot_mode_recovery_audit"."recovered_at"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."robot_mode_recovery_audit"."recovered_at" IS 'Backend time at which recovery or the already-IDLE no-op was committed.';


--
-- Name: scenario; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."scenario" (
    "id" "uuid" NOT NULL,
    "senior_id" "uuid" NOT NULL,
    "robot_id" "uuid" NOT NULL,
    "external_event_id" character varying(255),
    "scenario_type" character varying(50) NOT NULL,
    "final_status" character varying(50) NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "conversation_request" "jsonb",
    "active_navigation_command_id" character varying(64),
    "active_navigation_target" character varying(30),
    "trigger_context" "jsonb",
    "completion_result_code" character varying(50),
    "completion_reason_code" character varying(100),
    "follow_start_command_id" character varying(64),
    "follow_stop_command_id" character varying(64),
    "follow_start_requested_at" timestamp with time zone,
    "following_started_at" timestamp with time zone,
    "follow_stop_requested_at" timestamp with time zone,
    "last_follow_result_event_id" character varying(64),
    "last_follow_command_id" character varying(64),
    "last_follow_result_code" character varying(50),
    "last_follow_reason_code" character varying(100),
    "last_follow_result_at" timestamp with time zone,
    CONSTRAINT "ck_scenario_active_navigation_pair" CHECK ((("active_navigation_command_id" IS NULL) = ("active_navigation_target" IS NULL))),
    CONSTRAINT "ck_scenario_active_navigation_target" CHECK ((("active_navigation_target" IS NULL) OR (("active_navigation_target")::"text" = ANY ((ARRAY['LIVING_ROOM'::character varying, 'ENTRANCE'::character varying, 'DEFAULT'::character varying])::"text"[])))),
    CONSTRAINT "ck_scenario_conversation_request_object" CHECK ((("conversation_request" IS NULL) OR ("jsonb_typeof"("conversation_request") = 'object'::"text"))),
    CONSTRAINT "ck_scenario_follow_command_ids_differ" CHECK ((("follow_stop_command_id" IS NULL) OR ("follow_start_command_id" IS NULL) OR (("follow_stop_command_id")::"text" <> ("follow_start_command_id")::"text"))),
    CONSTRAINT "ck_scenario_follow_stop_correlation" CHECK (((("follow_stop_command_id" IS NULL) AND ("follow_stop_requested_at" IS NULL)) OR (("follow_stop_command_id" IS NOT NULL) AND ("follow_stop_requested_at" IS NOT NULL)))),
    CONSTRAINT "ck_scenario_trigger_context_object" CHECK ((("trigger_context" IS NULL) OR ("jsonb_typeof"("trigger_context") = 'object'::"text"))),
    CONSTRAINT "ck_scenario_wake_word_external_event" CHECK (((("scenario_type")::"text" <> 'WAKE_WORD_CALL'::"text") OR ("external_event_id" IS NOT NULL))),
    CONSTRAINT "ck_scenario_walk_start_correlation" CHECK (((("scenario_type")::"text" <> 'WALK'::"text") OR (("external_event_id" IS NOT NULL) AND ("follow_start_command_id" IS NOT NULL) AND ("follow_start_requested_at" IS NOT NULL))))
);


--
-- Name: COLUMN "scenario"."created_at"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."scenario"."created_at" IS '시나리오 생성 시각. S15P11E102-283';


--
-- Name: COLUMN "scenario"."updated_at"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."scenario"."updated_at" IS '마지막 상태 전이 시각. 터미널 상태 행에서는 종료 시각을 뜻하며 쿨다운 판정이 읽는다. S15P11E102-283';


--
-- Name: COLUMN "scenario"."conversation_request"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."scenario"."conversation_request" IS '이동 전에 확정한 AI 대화 intent, 첫 문장, triggerContext JSON';


--
-- Name: COLUMN "scenario"."trigger_context"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."scenario"."trigger_context" IS '시나리오 최초 트리거의 최소 구조화 문맥. 원본 음성/전체 STT는 저장하지 않는다.';


--
-- Name: COLUMN "scenario"."completion_result_code"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."scenario"."completion_result_code" IS '시나리오를 끝낸 Robot 명령의 안정적인 resultCode.';


--
-- Name: COLUMN "scenario"."completion_reason_code"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."scenario"."completion_reason_code" IS '실패·취소·시간초과의 안정적인 reasonCode. 사람용 자유 문장은 저장하지 않는다.';


--
-- Name: COLUMN "scenario"."follow_start_command_id"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."scenario"."follow_start_command_id" IS '산책 FOLLOW_START commandId. STARTED 뒤에도 자체 종료 상관관계를 위해 보존한다.';


--
-- Name: COLUMN "scenario"."follow_stop_command_id"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN "public"."scenario"."follow_stop_command_id" IS '산책 FOLLOW_STOP commandId. FOLLOW_START와 별개의 명령 식별자다.';


--
-- Name: wake_word_trigger_receipt; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."wake_word_trigger_receipt" (
    "event_id" character varying(64) NOT NULL,
    "robot_device_id" character varying(64) NOT NULL,
    "occurred_at" timestamp with time zone NOT NULL,
    "keyword" character varying(20) NOT NULL,
    "confidence" double precision,
    "disposition" character varying(40) NOT NULL,
    "scenario_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_wake_word_trigger_confidence" CHECK ((("confidence" IS NULL) OR (("confidence" >= (0)::double precision) AND ("confidence" <= (1)::double precision)))),
    CONSTRAINT "ck_wake_word_trigger_resolution" CHECK ((((("disposition")::"text" = 'RECEIVED'::"text") AND ("scenario_id" IS NULL)) OR ((("disposition")::"text" = 'ACCEPTED'::"text") AND ("scenario_id" IS NOT NULL)) OR ((("disposition")::"text" ~~ 'REJECTED_%'::"text") AND ("scenario_id" IS NULL))))
);


--
-- Name: walk_request_receipt; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."walk_request_receipt" (
    "id" "uuid" NOT NULL,
    "ingress" character varying(30) NOT NULL,
    "request_id" character varying(64) NOT NULL,
    "robot_device_id" character varying(64) NOT NULL,
    "action" character varying(10) NOT NULL,
    "source" character varying(10) NOT NULL,
    "conversation_id" "uuid",
    "occurred_at" timestamp with time zone NOT NULL,
    "disposition" character varying(50) NOT NULL,
    "scenario_id" "uuid",
    "scenario_status" character varying(50),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_walk_request_action" CHECK ((("action")::"text" = ANY ((ARRAY['START'::character varying, 'STOP'::character varying])::"text"[]))),
    CONSTRAINT "ck_walk_request_ingress" CHECK ((("ingress")::"text" = ANY ((ARRAY['MQTT'::character varying, 'GUARDIAN_REST'::character varying])::"text"[]))),
    CONSTRAINT "ck_walk_request_resolution" CHECK ((((("disposition")::"text" = 'RECEIVED'::"text") AND ("scenario_id" IS NULL) AND ("scenario_status" IS NULL)) OR ((("disposition")::"text" = ANY ((ARRAY['ACCEPTED'::character varying, 'NO_OP_ALREADY_STOPPING'::character varying])::"text"[])) AND ("scenario_id" IS NOT NULL) AND ("scenario_status" IS NOT NULL)) OR ((("disposition")::"text" ~~ 'REJECTED_%'::"text") AND ("scenario_id" IS NULL) AND ("scenario_status" IS NULL)))),
    CONSTRAINT "ck_walk_request_source" CHECK ((("source")::"text" = ANY ((ARRAY['VOICE'::character varying, 'APP'::character varying])::"text"[])))
);


--
-- Name: TABLE "walk_request_receipt"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE "public"."walk_request_receipt" IS 'Voice MQTT eventId와 Guardian REST requestId의 수락·거절을 재시작 뒤에도 재생하는 멱등 장부.';


--
-- Data for Name: app_user; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."app_user" ("id", "user_type", "name", "email", "preferred_name", "conversation_preferences", "onboarding_status", "time_zone", "personalization_consent_status", "health_data_consent_status", "schedule_consent_status", "guardian_sharing_consent_status", "status", "created_at", "updated_at", "quiet_hours_start", "quiet_hours_end", "home_latitude", "home_longitude", "birth_date", "wake_time", "sleep_time", "chronic_pain_area", "preferred_hospital", "home_address") FROM stdin;
10000000-0000-4000-8000-000000000001	SENIOR	김순자	kim.sunja@example.invalid	순자님	{"volume": "LOUD", "speechRate": "SLOW", "repeatWhenUnclear": true}	COMPLETED	Asia/Seoul	GRANTED	GRANTED	GRANTED	GRANTED	ACTIVE	2026-07-04 13:46:57.866887+00	2026-08-03 13:36:57.866887+00	22:00:00	07:00:00	\N	\N	\N	\N	\N	\N	\N	\N
10000000-0000-4000-8000-000000000002	GUARDIAN	우동균	woo.donggyun@example.invalid	\N	{}	NOT_STARTED	Asia/Seoul	NOT_ASKED	NOT_ASKED	NOT_ASKED	NOT_ASKED	ACTIVE	2026-07-04 13:46:57.866887+00	2026-08-03 13:36:57.866887+00	22:00:00	07:00:00	\N	\N	\N	\N	\N	\N	\N	\N
10000000-0000-4000-8000-000000000003	GUARDIAN	차서영	cha.seoyoung@example.invalid	\N	{}	NOT_STARTED	Asia/Seoul	NOT_ASKED	NOT_ASKED	NOT_ASKED	NOT_ASKED	ACTIVE	2026-07-04 13:46:57.866887+00	2026-08-03 13:36:57.866887+00	22:00:00	07:00:00	\N	\N	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: care_record; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."care_record" ("id", "senior_id", "parent_record_id", "scenario_id", "source_conversation_id", "source_message_id", "recipient_guardian_id", "created_by_user_id", "source_candidate_id", "record_type", "status", "details", "recurrence", "notification_tier", "occurred_at") FROM stdin;
80000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	10000000-0000-4000-8000-000000000002	10000000-0000-4000-8000-000000000001	60000000-0000-4000-8000-000000000001	MEDICATION	ACTIVE	{"dose": 1, "doseUnit": "정", "sourceType": "ONBOARDING_ANSWER", "instruction": "매 끼니 식후 30분", "medicationName": "관절염약", "verificationStatus": "USER_CONFIRMED"}	\N	\N	\N
d370aaf8-b95b-469f-bb41-47f1b634dea0	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	ENVIRONMENT_OBSERVATION	ACTIVE	{"temperatureC": 32.0, "humidityPercent": 50.0, "comfortAssessment": "UNCOMFORTABLE"}	\N	\N	2026-08-03 13:40:59+00
c16b1044-154e-464d-b315-5da6d57d82f2	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	ENVIRONMENT_OBSERVATION	ACTIVE	{"temperatureC": 32.0, "humidityPercent": 50.0, "comfortAssessment": "UNCOMFORTABLE"}	\N	\N	2026-08-03 13:47:53+00
4751dcb9-e8f3-4a86-a619-86e0e8b1dc9c	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	ENVIRONMENT_OBSERVATION	ACTIVE	{"temperatureC": 32.0, "humidityPercent": 50.0, "comfortAssessment": "UNCOMFORTABLE"}	\N	\N	2026-08-03 13:48:33+00
0e9ddbe7-ff7e-4123-8ca6-2711a921ca01	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	MEDICATION	ACTIVE	{"dose": "1정", "medicationName": "테스트약", "reminderEnabled": true}	\N	\N	\N
1d3f79d3-1e75-41fd-bd0e-d2a22ded3973	10000000-0000-4000-8000-000000000001	0e9ddbe7-ff7e-4123-8ca6-2711a921ca01	\N	\N	\N	\N	\N	\N	MEDICATION_SCHEDULE	ACTIVE	{"timeZone": "Asia/Seoul", "localTimes": ["09:57"], "medicationName": "테스트약", "reminderLeadMinutes": 1}	{"times": ["09:57"], "frequency": "DAILY"}	\N	\N
5eb8c18a-444c-413f-8650-dce622e26e17	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	MEDICATION	ACTIVE	{"dose": "1정", "medicationName": "테스트약", "reminderEnabled": true}	\N	\N	\N
5af4cc27-c791-4169-a15f-f971791cc6fb	10000000-0000-4000-8000-000000000001	5eb8c18a-444c-413f-8650-dce622e26e17	\N	\N	\N	\N	\N	\N	MEDICATION_SCHEDULE	ACTIVE	{"timeZone": "Asia/Seoul", "localTimes": ["10:11"], "medicationName": "테스트약", "reminderLeadMinutes": 1}	{"times": ["10:11"], "frequency": "DAILY"}	\N	\N
cb2af192-7d7a-442f-9d8b-1d0b6a4d180e	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	MEDICATION	ACTIVE	{"dose": "1정", "medicationName": "테스트약", "reminderEnabled": true}	\N	\N	\N
efd46610-aa83-44b8-b038-b6a35c5ccb6c	10000000-0000-4000-8000-000000000001	cb2af192-7d7a-442f-9d8b-1d0b6a4d180e	\N	\N	\N	\N	\N	\N	MEDICATION_SCHEDULE	ACTIVE	{"timeZone": "Asia/Seoul", "localTimes": ["10:14"], "medicationName": "테스트약", "reminderLeadMinutes": 1}	{"times": ["10:14"], "frequency": "DAILY"}	\N	\N
7ef44984-820c-46eb-b7a9-e6544cd18528	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	MEDICATION	ACTIVE	{"dose": "1정", "medicationName": "테스트약", "reminderEnabled": true}	\N	\N	\N
71338202-b45d-4a80-a59b-eee5bd9c94d2	10000000-0000-4000-8000-000000000001	7ef44984-820c-46eb-b7a9-e6544cd18528	\N	\N	\N	\N	\N	\N	MEDICATION_SCHEDULE	ACTIVE	{"timeZone": "Asia/Seoul", "localTimes": ["10:15"], "medicationName": "테스트약", "reminderLeadMinutes": 1}	{"times": ["10:15"], "frequency": "DAILY"}	\N	\N
673d84e4-d078-4cdd-9c97-b702b64dc4cd	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	ENVIRONMENT_OBSERVATION	ACTIVE	{"temperatureC": 31.0, "humidityPercent": 50.0, "comfortAssessment": "UNCOMFORTABLE"}	\N	\N	2026-08-05 11:53:37+00
7d183fb3-baa1-420d-9ae3-6ca57c5cf8a8	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	MEDICATION	ACTIVE	{"dose": "1?", "purpose": "????", "instruction": "??? ? ??", "medicationName": "??????", "reminderEnabled": true, "activeIngredient": "??"}	\N	\N	\N
cde96a24-2c4b-4549-a911-438d55c75f76	10000000-0000-4000-8000-000000000001	7d183fb3-baa1-420d-9ae3-6ca57c5cf8a8	\N	\N	\N	\N	\N	\N	MEDICATION_SCHEDULE	ACTIVE	{"timeZone": "Asia/Seoul", "localTimes": ["20:58"], "medicationName": "??????", "reminderLeadMinutes": 2}	{"times": ["20:58"], "frequency": "DAILY"}	\N	\N
3fd8f0ec-0df1-4df1-b126-91a505408156	10000000-0000-4000-8000-000000000001	\N	\N	\N	\N	\N	\N	\N	ENVIRONMENT_OBSERVATION	ACTIVE	{"temperatureC": 31.0, "humidityPercent": 50.0, "comfortAssessment": "UNCOMFORTABLE"}	\N	\N	2026-08-05 11:53:37+00
80000000-0000-4000-8000-000000000002	10000000-0000-4000-8000-000000000001	80000000-0000-4000-8000-000000000001	40000000-0000-4000-8000-000000000001	50000000-0000-4000-8000-000000000001	51000000-0000-4000-8000-000000000010	10000000-0000-4000-8000-000000000002	10000000-0000-4000-8000-000000000001	60000000-0000-4000-8000-000000000002	MEDICATION_SCHEDULE	ACTIVE	{"timeZone": "Asia/Seoul", "mealTimes": ["08:00", "12:00", "18:00"], "localTimes": ["08:30", "12:30", "18:30"], "sourceType": "CONVERSATION_MESSAGE", "instruction": "매 끼니 식후 30분", "medicationName": "관절염약", "verificationStatus": "USER_CONFIRMED"}	{"times": ["08:30", "12:30", "18:30"], "frequency": "DAILY"}	\N	\N
\.


--
-- Data for Name: care_relationship; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."care_relationship" ("id", "senior_id", "guardian_id", "priority", "status", "connected_at", "care_management_permission_status", "care_management_permission_updated_at", "care_management_permission_granted_by_user_id") FROM stdin;
11000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000002	PRIMARY	ACTIVE	2026-07-14 13:46:57.866887+00	GRANTED	2026-08-03 12:16:57.866887+00	10000000-0000-4000-8000-000000000001
11000000-0000-4000-8000-000000000002	10000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000003	SECONDARY	ACTIVE	2026-07-14 13:46:57.866887+00	NOT_ASKED	\N	\N
\.


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."conversation" ("id", "senior_id", "scenario_id", "status", "started_at", "ended_at", "raw_messages_expires_at", "sealed", "start_command_id", "ai_started_at", "end_outcome", "reason_code") FROM stdin;
50000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	40000000-0000-4000-8000-000000000001	COMPLETED	2026-08-03 13:16:57.866887+00	2026-08-03 13:26:57.866887+00	2026-09-02 13:46:57.866887+00	f	\N	\N	\N	\N
5d2d041d-ee86-48fd-b87a-35e8a3b92ea1	10000000-0000-4000-8000-000000000001	1975805e-78bc-4049-b588-f9cad3db7b56	FAILED	2026-08-05 11:53:40.083185+00	2026-08-05 11:58:40.747137+00	\N	f	1ff8a114-d6a5-4189-8d49-a45435b96d3d	\N	FAILED	AI_START_TIMEOUT
\.


--
-- Data for Name: conversation_message; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."conversation_message" ("id", "conversation_id", "sequence_no", "role", "content", "occurred_at", "created_at", "trigger_type", "priority", "orientation_question") FROM stdin;
51000000-0000-4000-8000-000000000001	50000000-0000-4000-8000-000000000001	1	ROBOT	순자님, 현재 복용하고 계신 약이 있나요?	2026-08-03 13:17:57.866887+00	2026-08-03 13:17:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000002	50000000-0000-4000-8000-000000000001	2	SENIOR	관절염약을 먹고 있어.	2026-08-03 13:18:57.866887+00	2026-08-03 13:18:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000003	50000000-0000-4000-8000-000000000001	3	ROBOT	한 번에 얼마나 드시나요?	2026-08-03 13:19:57.866887+00	2026-08-03 13:19:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000004	50000000-0000-4000-8000-000000000001	4	SENIOR	한 알씩 먹어.	2026-08-03 13:20:57.866887+00	2026-08-03 13:20:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000005	50000000-0000-4000-8000-000000000001	5	ROBOT	언제 복용하시나요?	2026-08-03 13:21:57.866887+00	2026-08-03 13:21:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000006	50000000-0000-4000-8000-000000000001	6	SENIOR	아침, 점심, 저녁을 먹고 30분 뒤에 먹어.	2026-08-03 13:22:57.866887+00	2026-08-03 13:22:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000007	50000000-0000-4000-8000-000000000001	7	ROBOT	평소 식사 시간은 언제인가요?	2026-08-03 13:23:57.866887+00	2026-08-03 13:23:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000008	50000000-0000-4000-8000-000000000001	8	SENIOR	아침 8시, 점심 12시, 저녁 6시쯤이야.	2026-08-03 13:24:57.866887+00	2026-08-03 13:24:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000009	50000000-0000-4000-8000-000000000001	9	ROBOT	관절염약 한 정을 매일 8시 30분, 12시 30분, 18시 30분에 복용하는 것으로 저장할까요?	2026-08-03 13:25:57.866887+00	2026-08-03 13:25:57.866887+00	\N	\N	\N
51000000-0000-4000-8000-000000000010	50000000-0000-4000-8000-000000000001	10	SENIOR	응, 그렇게 해.	2026-08-03 13:26:57.866887+00	2026-08-03 13:26:57.866887+00	\N	\N	\N
\.


--
-- Data for Name: conversation_summary; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."conversation_summary" ("id", "senior_id", "conversation_id", "summary_type", "period_started_at", "period_ended_at", "content", "source_message_count", "generated_at", "superseded_by_id", "embedding_status", "embedding_synced_at", "embedding_model") FROM stdin;
52000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	50000000-0000-4000-8000-000000000001	CONVERSATION	2026-08-03 13:16:57.866887+00	2026-08-03 13:26:57.866887+00	김순자는 관절염약을 한 번에 1정씩 매일 세 끼 식후 30분에 복용한다. 평소 식사 시각은 08:00, 12:00, 18:00이다.	10	2026-08-03 13:27:57.866887+00	\N	PENDING	\N	\N
\.


--
-- Data for Name: daily_activity_metric; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."daily_activity_metric" ("id", "senior_id", "metric_date", "medication_taken_count", "medication_scheduled_count", "meal_count", "water_intake_count", "sleep_minutes", "mood_score", "senior_utterance_count", "robot_utterance_count", "outing_count", "created_at", "updated_at", "orientation_question_repeat_count", "summary_sent_at") FROM stdin;
\.


--
-- Data for Name: fact_candidate; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."fact_candidate" ("id", "senior_id", "source_type", "onboarding_answer_id", "conversation_id", "source_message_id", "target_domain", "fact_type", "operation", "target_entity_id", "proposed_value", "confirmed_value", "missing_fields", "risk_level", "status", "clarification_reason", "clarification_count", "initiated_by_user_id", "confirmed_by_user_id", "requires_coordination", "coordination_status", "senior_position", "primary_guardian_decision", "primary_guardian_id", "contact_attempt_count", "last_contact_attempted_at", "unreachable_reason", "coordination_deadline_at", "coordination_completed_at", "coordination_note", "materialized_target_id", "materialized_at", "created_at", "updated_at", "confirmed_at", "expires_at") FROM stdin;
60000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	ONBOARDING_ANSWER	31000000-0000-4000-8000-000000000007	\N	\N	CARE_RECORD	MEDICATION	CREATE	\N	{"dose": 1, "doseUnit": "정", "medicationName": "관절염약"}	{"dose": 1, "doseUnit": "정", "medicationName": "관절염약"}	{}	SENSITIVE	MATERIALIZED	\N	0	10000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	f	NOT_REQUIRED	AGREED	PENDING	\N	0	\N	\N	\N	\N	\N	80000000-0000-4000-8000-000000000001	2026-08-03 12:11:57.866887+00	2026-08-03 12:08:57.866887+00	2026-08-03 12:11:57.866887+00	2026-08-03 12:10:57.866887+00	\N
60000000-0000-4000-8000-000000000002	10000000-0000-4000-8000-000000000001	CONVERSATION_MESSAGE	\N	50000000-0000-4000-8000-000000000001	51000000-0000-4000-8000-000000000010	CARE_RECORD	MEDICATION_SCHEDULE	CREATE	\N	{"timeZone": "Asia/Seoul", "mealTimes": ["08:00", "12:00", "18:00"], "localTimes": ["08:30", "12:30", "18:30"], "instruction": "매 끼니 식후 30분", "medicationName": "관절염약"}	{"timeZone": "Asia/Seoul", "mealTimes": ["08:00", "12:00", "18:00"], "localTimes": ["08:30", "12:30", "18:30"], "instruction": "매 끼니 식후 30분", "medicationName": "관절염약"}	{}	SENSITIVE	MATERIALIZED	\N	0	10000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	f	NOT_REQUIRED	AGREED	PENDING	\N	0	\N	\N	\N	\N	\N	80000000-0000-4000-8000-000000000002	2026-08-03 13:28:57.866887+00	2026-08-03 13:27:57.866887+00	2026-08-03 13:28:57.866887+00	2026-08-03 13:28:57.866887+00	\N
\.


--
-- Data for Name: flyway_schema_history; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."flyway_schema_history" ("installed_rank", "version", "description", "type", "script", "checksum", "installed_by", "installed_on", "execution_time", "success") FROM stdin;
1	1	init	SQL	V1__init.sql	1033169352	bomi	2026-08-03 22:19:53.674722	22	t
2	2	add robot runtime columns	SQL	V2__add_robot_runtime_columns.sql	-81615861	bomi	2026-08-03 22:19:53.730081	7	t
3	3	create occupancy event	SQL	V3__create_occupancy_event.sql	1830400641	bomi	2026-08-03 22:19:53.753407	5	t
4	4	create daily activity metric	SQL	V4__create_daily_activity_metric.sql	-913308021	bomi	2026-08-03 22:19:53.770801	4	t
5	5	add embedding sync columns	SQL	V5__add_embedding_sync_columns.sql	-910968745	bomi	2026-08-03 22:19:53.787881	6	t
6	6	add daily summary columns	SQL	V6__add_daily_summary_columns.sql	711235806	bomi	2026-08-03 22:19:53.806259	5	t
7	7	add care record occurred at	SQL	V7__add_care_record_occurred_at.sql	1613940706	bomi	2026-08-03 22:19:53.8235	15	t
8	8	add scenario timestamps	SQL	V8__add_scenario_timestamps.sql	-902713558	bomi	2026-08-03 22:19:53.854246	14	t
9	9	add app user birth date	SQL	V9__add_app_user_birth_date.sql	-1032753679	bomi	2026-08-05 20:36:53.11691	11	t
10	10	create known person	SQL	V10__create_known_person.sql	-1335052163	bomi	2026-08-05 20:36:53.155431	11	t
11	11	add app user personalization columns	SQL	V11__add_app_user_personalization_columns.sql	-46258074	bomi	2026-08-05 20:36:53.182473	8	t
12	12	add conversation sealed	SQL	V12__add_conversation_sealed.sql	-118265774	bomi	2026-08-05 20:36:53.205105	5	t
13	13	add fact candidate dedup index	SQL	V13__add_fact_candidate_dedup_index.sql	202501410	bomi	2026-08-05 20:36:53.223559	5	t
14	14	add ai conversation runtime	SQL	V14__add_ai_conversation_runtime.sql	-1491701832	bomi	2026-08-05 20:36:53.241877	14	t
15	15	add wake word call runtime	SQL	V15__add_wake_word_call_runtime.sql	529353546	bomi	2026-08-05 20:36:53.272606	12	t
16	16	add walk runtime	SQL	V16__add_walk_runtime.sql	1241943982	bomi	2026-08-05 20:36:53.297348	9	t
17	17	add app user home address	SQL	V17__add_app_user_home_address.sql	1612594104	bomi	2026-08-06 15:09:53.017795	16	t
18	18	create robot mode recovery audit	SQL	V18__create_robot_mode_recovery_audit.sql	-1589435874	bomi	2026-08-06 15:09:53.062806	15	t
\.


--
-- Data for Name: known_person; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."known_person" ("id", "senior_id", "guardian_user_id", "display_name", "relationship", "is_deceased", "deceased_note", "lives_with", "contact_frequency", "last_mentioned_at", "created_at", "updated_at") FROM stdin;
\.


--
-- Data for Name: memory; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."memory" ("id", "senior_id", "source_conversation_id", "source_summary_id", "source_candidate_id", "superseded_by_id", "memory_type", "content", "verification_status", "lifecycle_status", "visibility", "keywords", "importance", "first_observed_at", "last_confirmed_at", "last_used_at", "embedding_status", "embedding_synced_at", "embedding_model") FROM stdin;
70000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	50000000-0000-4000-8000-000000000001	52000000-0000-4000-8000-000000000001	\N	\N	PREFERENCE	김순자는 로봇이 천천히 크고 명확하게 말하는 것을 선호한다.	USER_CONFIRMED	ACTIVE	PRIVATE	{천천히,명확하게,"대화 선호"}	3	2026-08-03 13:17:57.866887+00	2026-08-03 13:26:57.866887+00	\N	PENDING	\N	\N
70000000-0000-4000-8000-000000000002	10000000-0000-4000-8000-000000000001	50000000-0000-4000-8000-000000000001	52000000-0000-4000-8000-000000000001	\N	\N	DAILY_ROUTINE	김순자는 보통 08:00, 12:00, 18:00에 식사한다.	USER_CONFIRMED	ACTIVE	SHARED_WITH_PRIMARY	{식사,08:00,12:00,18:00}	4	2026-08-03 12:04:57.866887+00	2026-08-03 13:26:57.866887+00	\N	PENDING	\N	\N
\.


--
-- Data for Name: occupancy_event; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."occupancy_event" ("id", "senior_id", "robot_id", "direction", "source", "resulting_occupancy", "occurred_at", "reported_at", "created_at") FROM stdin;
\.


--
-- Data for Name: onboarding_answer; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."onboarding_answer" ("id", "session_id", "question_code", "answer_value", "answered_channel", "respondent_user_id", "source_conversation_id", "source_message_id", "verification_status", "confirmed_by_user_id", "answered_at", "confirmed_at", "updated_at") FROM stdin;
31000000-0000-4000-8000-000000000001	30000000-0000-4000-8000-000000000001	PERSONALIZATION_CONSENT	{"consentStatus": "GRANTED"}	ROBOT	10000000-0000-4000-8000-000000000001	\N	\N	USER_CONFIRMED	10000000-0000-4000-8000-000000000001	2026-08-03 11:47:57.866887+00	2026-08-03 11:48:57.866887+00	2026-08-03 11:48:57.866887+00
31000000-0000-4000-8000-000000000002	30000000-0000-4000-8000-000000000001	HEALTH_DATA_CONSENT	{"consentStatus": "GRANTED"}	ROBOT	10000000-0000-4000-8000-000000000001	\N	\N	USER_CONFIRMED	10000000-0000-4000-8000-000000000001	2026-08-03 11:50:57.866887+00	2026-08-03 11:51:57.866887+00	2026-08-03 11:51:57.866887+00
31000000-0000-4000-8000-000000000003	30000000-0000-4000-8000-000000000001	SCHEDULE_CONSENT	{"consentStatus": "GRANTED"}	ROBOT	10000000-0000-4000-8000-000000000001	\N	\N	USER_CONFIRMED	10000000-0000-4000-8000-000000000001	2026-08-03 11:53:57.866887+00	2026-08-03 11:54:57.866887+00	2026-08-03 11:54:57.866887+00
31000000-0000-4000-8000-000000000004	30000000-0000-4000-8000-000000000001	GUARDIAN_SHARING_CONSENT	{"consentStatus": "GRANTED"}	ROBOT	10000000-0000-4000-8000-000000000001	\N	\N	USER_CONFIRMED	10000000-0000-4000-8000-000000000001	2026-08-03 11:56:57.866887+00	2026-08-03 11:57:57.866887+00	2026-08-03 11:57:57.866887+00
31000000-0000-4000-8000-000000000005	30000000-0000-4000-8000-000000000001	PREFERRED_NAME	{"preferredName": "순자님"}	ROBOT	10000000-0000-4000-8000-000000000001	\N	\N	USER_CONFIRMED	10000000-0000-4000-8000-000000000001	2026-08-03 12:00:57.866887+00	2026-08-03 12:01:57.866887+00	2026-08-03 12:01:57.866887+00
31000000-0000-4000-8000-000000000006	30000000-0000-4000-8000-000000000001	DAILY_ROUTINE	{"content": "보통 아침 8시, 점심 12시, 저녁 6시에 식사한다.", "keywords": ["식사", "생활 습관"]}	ROBOT	10000000-0000-4000-8000-000000000001	\N	\N	USER_CONFIRMED	10000000-0000-4000-8000-000000000001	2026-08-03 12:04:57.866887+00	2026-08-03 12:05:57.866887+00	2026-08-03 12:05:57.866887+00
31000000-0000-4000-8000-000000000007	30000000-0000-4000-8000-000000000001	MEDICATION	{"dose": 1, "doseUnit": "정", "medicationName": "관절염약"}	ROBOT	10000000-0000-4000-8000-000000000001	\N	\N	USER_CONFIRMED	10000000-0000-4000-8000-000000000001	2026-08-03 12:08:57.866887+00	2026-08-03 12:09:57.866887+00	2026-08-03 12:09:57.866887+00
31000000-0000-4000-8000-000000000008	30000000-0000-4000-8000-000000000001	PRIMARY_GUARDIAN_CARE_MANAGEMENT_CONSENT	{"guardianId": "10000000-0000-4000-8000-000000000002", "consentStatus": "GRANTED"}	ROBOT	10000000-0000-4000-8000-000000000001	\N	\N	USER_CONFIRMED	10000000-0000-4000-8000-000000000001	2026-08-03 12:12:57.866887+00	2026-08-03 12:13:57.866887+00	2026-08-03 12:13:57.866887+00
\.


--
-- Data for Name: onboarding_session; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."onboarding_session" ("id", "senior_id", "robot_id", "question_set_version", "started_channel", "status", "current_question_code", "started_at", "completed_at", "ended_at") FROM stdin;
30000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	onboarding-v1	ROBOT	COMPLETED	\N	2026-08-03 11:46:57.866887+00	2026-08-03 12:16:57.866887+00	2026-08-03 12:16:57.866887+00
\.


--
-- Data for Name: robot; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."robot" ("id", "senior_id", "device_id", "current_mode", "ambient_temperature_c", "ambient_humidity_percent", "ambient_observed_at", "is_active", "occupancy_status", "occupancy_observed_at", "door_node_heartbeat_at") FROM stdin;
20000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	bomi-AA001	IDLE	31.00	50.00	2026-08-05 11:53:37+00	t	UNKNOWN	\N	\N
\.


--
-- Data for Name: robot_mode_recovery_audit; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."robot_mode_recovery_audit" ("id", "robot_id", "robot_device_id", "operator_id", "previous_mode", "target_mode", "disposition", "physical_safety_confirmed", "reason", "recovered_at") FROM stdin;
62464cfe-bce8-4b62-b393-dd8adbf87992	20000000-0000-4000-8000-000000000001	bomi-AA001	wakeword-demo-local	SAFE_STOP	IDLE	RECOVERED	t	wakeword demo recovery	2026-08-06 06:15:39.921733+00
\.


--
-- Data for Name: scenario; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."scenario" ("id", "senior_id", "robot_id", "external_event_id", "scenario_type", "final_status", "created_at", "updated_at", "conversation_request", "active_navigation_command_id", "active_navigation_target", "trigger_context", "completion_result_code", "completion_reason_code", "follow_start_command_id", "follow_stop_command_id", "follow_start_requested_at", "following_started_at", "follow_stop_requested_at", "last_follow_result_event_id", "last_follow_command_id", "last_follow_result_code", "last_follow_reason_code", "last_follow_result_at") FROM stdin;
40000000-0000-4000-8000-000000000001	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	seed-kim-sunja-manual-001	MANUAL_INTERACTION	COMPLETED	2026-08-03 11:46:57.866887+00	2026-08-03 11:46:57.866887+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
a1f56aad-0237-4c35-8ee7-a21c11b527f5	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	ambient-sensor-01	WELLNESS_CHECK	COMPLETED	2026-08-03 13:47:23.551525+00	2026-08-03 13:50:48.591985+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
82a89665-c982-457c-8163-28192bf8a0b0	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	door_sensor	HOMECOMING	CANCELLED	2026-08-03 13:54:29.91733+00	2026-08-04 01:14:19.502704+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
4d4dbd39-519f-49a2-aa21-68d3219b4b71	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	med-5af4cc27-c791-4169-a15f-f971791cc6fb-2026-08-04-10:11	MEDICATION_REMINDER	TIMED_OUT	2026-08-04 01:14:37.645214+00	2026-08-05 11:36:57.634792+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
2b6a52ae-88f9-4563-8263-9d21dbb89e6c	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	0a17aeac-de3c-4d97-82e8-11312d9a19f0	WAKE_WORD_CALL	COMPLETED	2026-08-05 11:48:41.829094+00	2026-08-05 11:48:44.201539+00	\N	\N	\N	{"keyword": "보미야", "robotId": "bomi-AA001", "confidence": 0.95, "occurredAt": "2026-08-05T20:48:41+09:00"}	ARRIVED	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
c8f00c00-6b23-4b18-bb7b-6b54d2546304	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	8164eb2e-b73e-4e4d-b7ae-a653bacaf6b6	WALK	COMPLETED	2026-08-05 11:51:10.447355+00	2026-08-05 11:52:50.684735+00	\N	\N	\N	{"source": "VOICE", "ingress": "MQTT", "occurredAt": "2026-08-05T20:51:10+09:00"}	STOPPED	\N	a6fd40d3-9d91-4b17-82e2-ebf3d74ae87f	23357d88-57f6-4e29-ba1b-f1de6fd2999f	2026-08-05 11:51:10.447356+00	2026-08-05 11:51:10.464179+00	2026-08-05 11:52:50.673299+00	a23ab160-aded-436d-a0e3-71636ae3afd0	23357d88-57f6-4e29-ba1b-f1de6fd2999f	STOPPED	\N	2026-08-05 11:52:50+00
1975805e-78bc-4049-b588-f9cad3db7b56	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	ambient-sensor-01	WELLNESS_CHECK	TIMED_OUT	2026-08-05 11:53:38.063737+00	2026-08-06 06:09:57.635499+00	{"text": "어르신, 방 안 공기가 심상치 않네요. 좀 어떠세요?", "intent": "WELLNESS_CHECK", "triggerContext": {"location": "LIVING_ROOM", "sourceId": "ambient-sensor-01", "temperatureC": 31.0, "humidityPercent": 50.0}}	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
eca50e48-10ca-473b-95f8-fcd5a2429c8a	10000000-0000-4000-8000-000000000001	20000000-0000-4000-8000-000000000001	6a9b73b7-4521-4109-bc73-67a497ae3833	WAKE_WORD_CALL	COMPLETED	2026-08-06 06:46:01.480215+00	2026-08-06 06:46:04.843063+00	\N	\N	\N	{"keyword": "보미야", "robotId": "bomi-AA001", "occurredAt": "2026-08-06T06:46:01.485338Z"}	ARRIVED	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: wake_word_trigger_receipt; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."wake_word_trigger_receipt" ("event_id", "robot_device_id", "occurred_at", "keyword", "confidence", "disposition", "scenario_id", "created_at") FROM stdin;
0a17aeac-de3c-4d97-82e8-11312d9a19f0	bomi-AA001	2026-08-05 11:48:41+00	보미야	0.95	ACCEPTED	2b6a52ae-88f9-4563-8263-9d21dbb89e6c	2026-08-05 11:48:41.820523+00
99f4166d-a34e-4356-881b-8b49db1d9c97	bomi-AA001	2026-08-06 05:26:25.004341+00	보미야	0.99	REJECTED_SAFE_STOP	\N	2026-08-06 06:10:02.544427+00
6a9b73b7-4521-4109-bc73-67a497ae3833	bomi-AA001	2026-08-06 06:46:01.485338+00	보미야	\N	ACCEPTED	eca50e48-10ca-473b-95f8-fcd5a2429c8a	2026-08-06 06:46:01.478448+00
\.


--
-- Data for Name: walk_request_receipt; Type: TABLE DATA; Schema: public; Owner: -
--

COPY "public"."walk_request_receipt" ("id", "ingress", "request_id", "robot_device_id", "action", "source", "conversation_id", "occurred_at", "disposition", "scenario_id", "scenario_status", "created_at") FROM stdin;
6048a9b1-c8cb-4d2f-8a7e-125d2af03dd4	MQTT	8164eb2e-b73e-4e4d-b7ae-a653bacaf6b6	bomi-AA001	START	VOICE	\N	2026-08-05 11:51:10+00	ACCEPTED	c8f00c00-6b23-4b18-bb7b-6b54d2546304	STARTING_FOLLOW	2026-08-05 11:51:10.409343+00
0d9897b4-c1c7-4e6f-b8f3-0b87d2de01cb	MQTT	5cf72289-3530-4161-a344-62bbc1cfdffe	bomi-AA001	START	VOICE	\N	2026-08-05 11:52:11+00	REJECTED_ACTIVE_SCENARIO	\N	\N	2026-08-05 11:52:11.770692+00
0c06e933-c3eb-4a72-b90b-667e793d0dd4	MQTT	e17274bf-a4a0-4106-949d-c824980c52eb	bomi-AA001	STOP	VOICE	\N	2026-08-05 11:52:50+00	ACCEPTED	c8f00c00-6b23-4b18-bb7b-6b54d2546304	STOPPING_FOLLOW	2026-08-05 11:52:50.664247+00
\.


--
-- Name: flyway_schema_history flyway_schema_history_pk; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."flyway_schema_history"
    ADD CONSTRAINT "flyway_schema_history_pk" PRIMARY KEY ("installed_rank");


--
-- Name: app_user pk_app_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."app_user"
    ADD CONSTRAINT "pk_app_user" PRIMARY KEY ("id");


--
-- Name: care_record pk_care_record; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."care_record"
    ADD CONSTRAINT "pk_care_record" PRIMARY KEY ("id");


--
-- Name: care_relationship pk_care_relationship; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."care_relationship"
    ADD CONSTRAINT "pk_care_relationship" PRIMARY KEY ("id");


--
-- Name: conversation pk_conversation; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."conversation"
    ADD CONSTRAINT "pk_conversation" PRIMARY KEY ("id");


--
-- Name: conversation_message pk_conversation_message; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."conversation_message"
    ADD CONSTRAINT "pk_conversation_message" PRIMARY KEY ("id");


--
-- Name: conversation_summary pk_conversation_summary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."conversation_summary"
    ADD CONSTRAINT "pk_conversation_summary" PRIMARY KEY ("id");


--
-- Name: daily_activity_metric pk_daily_activity_metric; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."daily_activity_metric"
    ADD CONSTRAINT "pk_daily_activity_metric" PRIMARY KEY ("id");


--
-- Name: fact_candidate pk_fact_candidate; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."fact_candidate"
    ADD CONSTRAINT "pk_fact_candidate" PRIMARY KEY ("id");


--
-- Name: known_person pk_known_person; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."known_person"
    ADD CONSTRAINT "pk_known_person" PRIMARY KEY ("id");


--
-- Name: memory pk_memory; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."memory"
    ADD CONSTRAINT "pk_memory" PRIMARY KEY ("id");


--
-- Name: occupancy_event pk_occupancy_event; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."occupancy_event"
    ADD CONSTRAINT "pk_occupancy_event" PRIMARY KEY ("id");


--
-- Name: onboarding_answer pk_onboarding_answer; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."onboarding_answer"
    ADD CONSTRAINT "pk_onboarding_answer" PRIMARY KEY ("id");


--
-- Name: onboarding_session pk_onboarding_session; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."onboarding_session"
    ADD CONSTRAINT "pk_onboarding_session" PRIMARY KEY ("id");


--
-- Name: robot pk_robot; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."robot"
    ADD CONSTRAINT "pk_robot" PRIMARY KEY ("id");


--
-- Name: scenario pk_scenario; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."scenario"
    ADD CONSTRAINT "pk_scenario" PRIMARY KEY ("id");


--
-- Name: robot_mode_recovery_audit robot_mode_recovery_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."robot_mode_recovery_audit"
    ADD CONSTRAINT "robot_mode_recovery_audit_pkey" PRIMARY KEY ("id");


--
-- Name: care_record uq_care_record_source_candidate; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."care_record"
    ADD CONSTRAINT "uq_care_record_source_candidate" UNIQUE ("source_candidate_id");


--
-- Name: conversation_message uq_conversation_message_seq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."conversation_message"
    ADD CONSTRAINT "uq_conversation_message_seq" UNIQUE ("conversation_id", "sequence_no");


--
-- Name: conversation uq_conversation_scenario; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."conversation"
    ADD CONSTRAINT "uq_conversation_scenario" UNIQUE ("scenario_id");


--
-- Name: conversation uq_conversation_start_command; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."conversation"
    ADD CONSTRAINT "uq_conversation_start_command" UNIQUE ("start_command_id");


--
-- Name: conversation_summary uq_conversation_summary_period; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."conversation_summary"
    ADD CONSTRAINT "uq_conversation_summary_period" UNIQUE ("senior_id", "summary_type", "period_started_at", "period_ended_at");


--
-- Name: daily_activity_metric uq_daily_activity_metric_day; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."daily_activity_metric"
    ADD CONSTRAINT "uq_daily_activity_metric_day" UNIQUE ("senior_id", "metric_date");


--
-- Name: memory uq_memory_source_candidate; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."memory"
    ADD CONSTRAINT "uq_memory_source_candidate" UNIQUE ("source_candidate_id");


--
-- Name: robot uq_robot_device_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."robot"
    ADD CONSTRAINT "uq_robot_device_id" UNIQUE ("device_id");


--
-- Name: scenario uq_scenario_active_navigation_command; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."scenario"
    ADD CONSTRAINT "uq_scenario_active_navigation_command" UNIQUE ("active_navigation_command_id");


--
-- Name: walk_request_receipt uq_walk_request_ingress_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."walk_request_receipt"
    ADD CONSTRAINT "uq_walk_request_ingress_request" UNIQUE ("ingress", "request_id");


--
-- Name: wake_word_trigger_receipt wake_word_trigger_receipt_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."wake_word_trigger_receipt"
    ADD CONSTRAINT "wake_word_trigger_receipt_pkey" PRIMARY KEY ("event_id");


--
-- Name: walk_request_receipt walk_request_receipt_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."walk_request_receipt"
    ADD CONSTRAINT "walk_request_receipt_pkey" PRIMARY KEY ("id");


--
-- Name: flyway_schema_history_s_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "flyway_schema_history_s_idx" ON "public"."flyway_schema_history" USING "btree" ("success");


--
-- Name: idx_conversation_summary_embedding_resync; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_conversation_summary_embedding_resync" ON "public"."conversation_summary" USING "btree" ("embedding_status") WHERE (("embedding_status")::"text" <> 'SYNCED'::"text");


--
-- Name: idx_known_person_senior; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_known_person_senior" ON "public"."known_person" USING "btree" ("senior_id");


--
-- Name: idx_memory_embedding_resync; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_memory_embedding_resync" ON "public"."memory" USING "btree" ("embedding_status") WHERE (("embedding_status")::"text" <> 'SYNCED'::"text");


--
-- Name: idx_occupancy_event_senior_occurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_occupancy_event_senior_occurred" ON "public"."occupancy_event" USING "btree" ("senior_id", "occurred_at");


--
-- Name: ix_care_record_senior_type_occurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ix_care_record_senior_type_occurred" ON "public"."care_record" USING "btree" ("senior_id", "record_type", "occurred_at");


--
-- Name: ix_conversation_active_ai; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ix_conversation_active_ai" ON "public"."conversation" USING "btree" ("ai_started_at") WHERE ((("status")::"text" = 'OPEN'::"text") AND ("start_command_id" IS NOT NULL) AND ("ai_started_at" IS NOT NULL));


--
-- Name: ix_conversation_pending_ai_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ix_conversation_pending_ai_start" ON "public"."conversation" USING "btree" ("started_at") WHERE ((("status")::"text" = 'OPEN'::"text") AND ("start_command_id" IS NOT NULL) AND ("ai_started_at" IS NULL));


--
-- Name: ix_robot_mode_recovery_audit_robot_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ix_robot_mode_recovery_audit_robot_time" ON "public"."robot_mode_recovery_audit" USING "btree" ("robot_id", "recovered_at" DESC);


--
-- Name: ix_scenario_active_walk_robot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ix_scenario_active_walk_robot" ON "public"."scenario" USING "btree" ("robot_id") WHERE ((("scenario_type")::"text" = 'WALK'::"text") AND (("final_status")::"text" <> ALL ((ARRAY['COMPLETED'::character varying, 'FAILED'::character varying, 'CANCELLED'::character varying, 'TIMED_OUT'::character varying])::"text"[])));


--
-- Name: ix_scenario_senior_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ix_scenario_senior_status" ON "public"."scenario" USING "btree" ("senior_id", "final_status");


--
-- Name: ix_scenario_senior_type_status_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ix_scenario_senior_type_status_updated" ON "public"."scenario" USING "btree" ("senior_id", "scenario_type", "final_status", "updated_at");


--
-- Name: uq_fact_candidate_senior_message_fact_type; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "uq_fact_candidate_senior_message_fact_type" ON "public"."fact_candidate" USING "btree" ("senior_id", "source_message_id", "fact_type") WHERE ("source_message_id" IS NOT NULL);


--
-- Name: INDEX "uq_fact_candidate_senior_message_fact_type"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX "public"."uq_fact_candidate_senior_message_fact_type" IS '같은 어르신·같은 발화·같은 factType 의 재시도 중복 제출을 막는다(S15P11E102-255). source_message_id 가 NULL 인 온보딩 경로는 이 인덱스 대상이 아니다.';


--
-- Name: uq_scenario_one_active_per_senior; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "uq_scenario_one_active_per_senior" ON "public"."scenario" USING "btree" ("senior_id") WHERE (("final_status")::"text" <> ALL ((ARRAY['COMPLETED'::character varying, 'FAILED'::character varying, 'CANCELLED'::character varying, 'TIMED_OUT'::character varying])::"text"[]));


--
-- Name: uq_scenario_wake_word_event; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "uq_scenario_wake_word_event" ON "public"."scenario" USING "btree" ("external_event_id") WHERE ((("scenario_type")::"text" = 'WAKE_WORD_CALL'::"text") AND ("external_event_id" IS NOT NULL));


--
-- PostgreSQL database dump complete
--

\unrestrict 38chcAVXyM98km4smRFhHF6d0q1D5OzopbYSsXMFhgM4HeBaieNxMZCfjnQqaji

