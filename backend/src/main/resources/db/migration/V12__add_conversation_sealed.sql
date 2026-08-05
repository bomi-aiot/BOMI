-- V12 : conversation 에 봉인(sealed) 플래그를 추가한다 (S15P11E102-254)
--
-- 이 티켓이 대화 요약 생성을 실제로 켠다 — 닫힌 대화의 원문이 처음으로 외부 생성형
-- LLM(Gemini) 에 전송된다. "우리끼리 얘기"로 봉인된 대화까지 그대로 보내면 그 약속을
-- 깨는 것이므로(CLAUDE.md §9 T4), 요약 대상에서 제외할 수 있는 표식이 먼저 있어야
-- 한다. Conversation.java 의 sealed 필드가 이미 이 컬럼을 매핑하고 있었다 — 이
-- 마이그레이션이 없으면 Hibernate ddl-auto=validate 가 기동 자체를 막는다.
--
-- 왜 NOT NULL + DEFAULT false 인가
--   봉인은 로봇(ai_chat)이 로컬에서 판정해 POST .../end 로 실어 보내는 값이다. 로봇
--   쪽 판정 로직이 아직 이 값을 채우지 않는 경로가 있어도(별도 AI 라인 작업), 서버는
--   "모른다"가 아니라 "봉인되지 않았다"로 취급해야 대화가 계속 정상적으로 요약된다.
--   과다 요약 쪽으로 실패하는 편이 "영원히 요약 안 됨" 쪽으로 실패하는 것보다 낫다는
--   판단이다(Conversation.java 의 sealed 필드 주석과 동일한 근거).
ALTER TABLE conversation
    ADD COLUMN sealed boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN conversation.sealed IS
    '이 대화가 "우리끼리 얘기"로 봉인됐는가. 봉인된 대화는 요약 생성(외부 생성형 '
    'LLM 호출) 대상에서 제외한다(CLAUDE.md §9 T4). 한 방향 플래그 — 해제 없음.';
