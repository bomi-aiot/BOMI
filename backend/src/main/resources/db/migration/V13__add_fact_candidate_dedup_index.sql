-- V13 : fact_candidate 에 (senior_id, source_message_id, fact_type) 부분 유니크 인덱스를
-- 추가한다 (S15P11E102-255)
--
-- 로봇의 추출 큐 flush(jobs/ticks.extraction_flush)는 최소 한 번(at-least-once) 제출을
-- 전제한다 — 네트워크 타임아웃 뒤 재시도가 실제로는 이미 성공한 제출을 다시 보낼 수
-- 있다. ConversationFactIntakeService 가 저장 전에 같은 조합을 조회해 애플리케이션
-- 레벨에서 먼저 막지만, 동시 요청 경합까지 막으려면 DB 제약이 마지막 방어선이어야
-- 한다.
--
-- source_message_id 를 부분(WHERE ... IS NOT NULL) 인덱스로 둔 이유
--   fact_candidate 는 온보딩 답변 경로(fromOnboardingAnswer)에서도 만들어지고, 그
--   경로는 source_message_id 가 NULL 이다. Postgres 의 일반 UNIQUE 제약은 NULL 을
--   서로 다른 값으로 취급해 중복을 막지 못하므로, 이 인덱스를 걸어도 온보딩 경로에는
--   아무 영향이 없다 — 그것이 바로 우리가 원하는 동작이다(대화 추출 경로만 dedup
--   대상이다).
CREATE UNIQUE INDEX uq_fact_candidate_senior_message_fact_type
    ON fact_candidate (senior_id, source_message_id, fact_type)
    WHERE source_message_id IS NOT NULL;

COMMENT ON INDEX uq_fact_candidate_senior_message_fact_type IS
    '같은 어르신·같은 발화·같은 factType 의 재시도 중복 제출을 막는다(S15P11E102-255). '
    'source_message_id 가 NULL 인 온보딩 경로는 이 인덱스 대상이 아니다.';
