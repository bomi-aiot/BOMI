-- forget-knee-topic.sql — "무릎" 이야기를 어르신 문맥에서 걷어낸다.
--
-- 왜 존재하는가
--   보미가 무릎을 너무 자주 화제로 삼는다. 원인은 모델이 아니라 **매 턴 프롬프트에
--   실려 나가는 DB 값**이다. app_user.chronic_pain_area 는 조건 없이 전 턴에 실리고
--   (prompts/builder.py _format_profile → "- 오래 아픈 부위: 양쪽 무릎, 허리"),
--   memory/summary 는 의미 검색 상위에 걸릴 때마다 다시 실린다. 눈앞에 있는 사실은
--   화제가 된다 — 빈 섹션을 프롬프트에 넣지 않는 것과 같은 이유다.
--
-- 언제 실행하는가
--   지금 한 번. 그리고 대화로 무릎 이야기가 다시 쌓였을 때.
--
-- ★ 실행 전에 반드시 1) 절의 SELECT 만 먼저 돌려서 무엇이 지워질지 눈으로 본다.
--   이 스크립트는 되돌릴 수 없는 삭제(conversation_message)를 포함한다.
--
-- 주의
--   * senior_id 를 확인하고 쓴다. 아래 기본값은 시드 데이터의 김순자다
--     (scripts/dev/seed-kim-sunja.sql). \set 과 :'senior_id' 는 psql 문법이므로
--     `psql -f scripts/dev/forget-knee-topic.sql` 로 실행한다. 다른 클라이언트를
--     쓴다면 :'senior_id' 를 UUID 리터럴로 직접 치환한다.
--   * care_record 의 '관절염약' 은 **건드리지 않는다.** 무릎과 관련은 있지만 복약
--     알림 시연(CLAUDE.md §5)이 그 행 하나에 걸려 있다. 지우면 시나리오가 죽는다.
--     복약 알림에서 약 이름을 바꾸고 싶으면 details->>'medicationName' 만 수정한다.
--   * Qdrant(외부 벡터 스토어)는 손대지 않아도 된다. QdrantMemorySearch 는 id 와
--     점수만 돌려주고 본문은 PostgreSQL 에서 다시 읽으며, 조회 대상은
--     lifecycle_status='ACTIVE' 뿐이다(MemoryRepository). 즉 아래 3) 로 상태만
--     바꿔도 벡터가 남아 본문을 되살릴 수는 없다 — 고아 벡터는 조용히 무시된다.
--   * 젯슨의 로컬 체크포인트(localstore/runtime.sqlite)에는 지난 대화 상태가 따로
--     남는다. DB 를 지워도 그쪽이 남아 있으면 한동안 무릎 이야기가 이어질 수 있다.
--     필요하면 로봇을 멈추고 그 파일을 지운 뒤 다시 띄운다.

\set senior_id '10000000-0000-4000-8000-000000000001'

-- 1) 먼저 본다 (이 절만 따로 실행) ------------------------------------------
--
--   지울 목록을 눈으로 확인하는 절이다. 여기서 예상 밖의 행이 보이면 멈춘다.
SELECT 'app_user.chronic_pain_area' AS source, chronic_pain_area AS content
  FROM app_user WHERE id = :'senior_id'::uuid AND chronic_pain_area IS NOT NULL
UNION ALL
SELECT 'memory:' || lifecycle_status, content
  FROM memory WHERE senior_id = :'senior_id'::uuid AND content LIKE '%무릎%'
UNION ALL
SELECT 'conversation_summary', content
  FROM conversation_summary WHERE senior_id = :'senior_id'::uuid AND content LIKE '%무릎%'
UNION ALL
SELECT 'fact_candidate:' || status, proposed_value::text
  FROM fact_candidate WHERE senior_id = :'senior_id'::uuid AND proposed_value::text LIKE '%무릎%'
UNION ALL
SELECT 'conversation_message:' || m.role, m.content
  FROM conversation_message m
  JOIN conversation c ON c.id = m.conversation_id
 WHERE c.senior_id = :'senior_id'::uuid AND m.content LIKE '%무릎%';

BEGIN;

-- 2) 프로필의 만성 통증 부위를 비운다  ★ 이 한 줄이 가장 크게 듣는다 -----------
--
--   나머지는 "검색에 걸렸을 때만" 실리지만 이 값은 매 턴 무조건 실린다. 컬럼은
--   nullable 이고(V11), 읽는 쪽은 값이 비면 그 줄 자체를 안 만든다
--   (prompts/builder.py, ConversationContextResponse "null when unset").
UPDATE app_user
   SET chronic_pain_area = NULL
 WHERE id = :'senior_id'::uuid;

-- 3) 장기 기억을 조회 대상에서 뺀다 ------------------------------------------
--
--   왜 DELETE 가 아니라 lifecycle_status 인가
--     DELETED 는 이 도메인이 가진 '지움'의 표현이고(MemoryLifecycleStatus), 조회는
--     ACTIVE 만 본다. 즉 효과는 삭제와 같으면서, 잘못 지웠을 때 되돌릴 수 있고
--     "무엇을 언제 걷어냈는지"가 남는다. 행을 정말 없애고 싶으면 아래 5) 를 쓴다.
UPDATE memory
   SET lifecycle_status = 'DELETED'
 WHERE senior_id = :'senior_id'::uuid
   AND content LIKE '%무릎%'
   AND lifecycle_status <> 'DELETED';

-- 4) 아직 확정되지 않은 사실 후보를 버린다 -----------------------------------
--
--   이걸 남기면 다음 대화에서 보미가 "무릎 아프신 거 맞죠?" 하고 되물어 확정을
--   시도한다 — 지운 것이 그 경로로 되돌아온다.
UPDATE fact_candidate
   SET status = 'REJECTED',
       updated_at = now()
 WHERE senior_id = :'senior_id'::uuid
   AND proposed_value::text LIKE '%무릎%'
   AND status NOT IN ('REJECTED', 'MATERIALIZED');

-- 4b) 온보딩 답변 ------------------------------------------------------------
--
--   OnboardingMaterializer 는 확정된 CHRONIC_PAIN_AREA 답변을
--   app_user.chronic_pain_area 로 옮긴다. 답변이 남아 있으면 온보딩을 다시 돌리거나
--   재확정하는 순간 2) 가 되돌아온다. (시드 데이터에는 이 답변이 없다 — 실제
--   운영 DB 에서만 걸린다.)
UPDATE onboarding_answer
   SET answer_value = NULL,
       updated_at = now()
 WHERE question_code = 'CHRONIC_PAIN_AREA'
   AND answer_value::text LIKE '%무릎%'
   AND session_id IN (
       SELECT id FROM onboarding_session WHERE senior_id = :'senior_id'::uuid);

-- 5) 요약과 원문 메시지 -------------------------------------------------------
--
--   요약은 superseded 로 감출 수단이 없어서(조회가 superseded_by_id IS NULL 을 보는
--   경로가 아니다) 지운다. 원문 메시지도 지운다 — 보존기간이 지나면 어차피 삭제되는
--   데이터다(raw_messages_expires_at).
--
--   ★ 여기부터는 되돌릴 수 없다. 1) 의 SELECT 를 확인하지 않았다면 멈춘다.
DELETE FROM conversation_summary
 WHERE senior_id = :'senior_id'::uuid
   AND content LIKE '%무릎%';

DELETE FROM conversation_message
 WHERE content LIKE '%무릎%'
   AND conversation_id IN (SELECT id FROM conversation WHERE senior_id = :'senior_id'::uuid);

COMMIT;

-- 6) 확인 --------------------------------------------------------------------
--
--   1) 과 같은 질의다. 남는 것은 lifecycle_status='DELETED' 인 memory 행뿐이어야
--   한다(조회되지 않는다). 그 행까지 없애려면:
--     DELETE FROM memory WHERE senior_id = :'senior_id'::uuid AND content LIKE '%무릎%';
