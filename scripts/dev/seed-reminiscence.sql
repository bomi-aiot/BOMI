-- seed-reminiscence.sql — 회상 대화를 위한 씨앗과 가족 명부.
--
-- 왜 존재하는가
--   회상은 이 제품이 하려는 일 자체다(CLAUDE.md §1, 기분과 인지에 실제 효과가 있다).
--   그런데 시연 DB 의 memory 20행은 전부 대화에서 자동 추출된 것이라, 어르신의 '삶'이
--   아니라 그날의 부스러기다("아이스에 등록하고 동 연동을 확인했다"). 그것만으로는
--   "그 여행 얘기 다시 해주세요" 같은 이어짐이 생기지 않는다.
--
-- ★ 이 파일의 내용은 '시연 페르소나'다
--   김순자는 실존 인물이 아니다(이메일이 @example.invalid 다). 아래 생애 사실은
--   시연을 위해 지어낸 것이며, 기존 canon(1946년생·부산 강서구·화분·트로트·주말에
--   오는 손자)과 어긋나지 않게 맞췄다. **실제 어르신에게 쓸 때는 전부 지우고 그분의
--   실제 이야기로 바꾼다.** 남의 삶을 지어내 들려주는 것은 이 로봇이 할 수 있는 가장
--   나쁜 실패에 가깝다.
--
-- 언제 실행하는가
--   한 번. 실행 후 임베딩 동기화 잡이 5분 안에 색인한다(EMBEDDING_SYNC_ENABLED=true
--   필요, 한 실행 상한 30행 — 이 파일은 10행이라 1회로 끝난다).
--
-- 실행
--   ssh bomi 'docker exec -i bomi-postgres psql -U bomi -d bomi' < scripts/dev/seed-reminiscence.sql

\set senior_id '10000000-0000-4000-8000-000000000001'

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1) 회상 씨앗
--
-- 랭킹은 관련도 × (importance/5) × 최근성 × 사용벌점이다
-- (ConversationContextService.score). 아래 값들이 그 식에 맞춰져 있다.
--
--   importance = 5
--     기존 20행은 대부분 NULL(=3 취급)이라, 상위 6건(policy.MEMORY_TOP_K) 경쟁에서
--     확실히 앞선다.
--
--   first_observed_at / last_confirmed_at = NULL   ★ 사건 연도를 넣지 않는다
--     최근성 가중치는 반감기 30일의 지수 감쇠다. "1965년"을 넣으면 점수가 0 에
--     수렴해 영원히 안 뽑힌다. 둘 다 NULL 이면 감점 없이 1.0 고정이다 — 늙지 않는
--     씨앗이 된다. (recencyWeight 의 reference == null 분기)
--
--   last_used_at = NULL
--     한 번도 안 쓴 기억은 사용벌점이 없다. 한 번 꺼내면 백엔드가 알아서 벌점을
--     매겨 잠시 뒤로 물리므로, 회전은 공짜로 된다.
--
--   keywords
--     의미 검색이 켜진 지금(2026-08-10)은 content 만으로도 매칭되지만, 임베딩이
--     꺼지거나 실패하면 키워드 폴백으로 되돌아간다. 그때 이 배열이 유일한 매칭
--     수단이다 — 값이 싸므로 채워 둔다.
--
--   visibility
--     PRIVATE 은 보호자 화면에 안 나온다. 생애 이야기는 보호자가 알아도 좋은
--     것이므로 SHARED_WITH_PRIMARY 로 두되, 사적인 감정이 실린 것은 PRIVATE 로
--     남긴다.
--
-- 한 행에 한 사실, 구체적으로 쓴다. 모델은 이 문장을 거의 그대로 화제로 삼는다.
-- "아이들을 좋아하셨다"보다 "가을 운동회 준비를 제일 즐거워하셨다"가 대화를 만든다.
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO memory (
    id, senior_id, memory_type, content, verification_status, lifecycle_status,
    visibility, keywords, importance,
    first_observed_at, last_confirmed_at, last_used_at,
    embedding_status
) VALUES
-- 교사로 산 30년 — 이 어르신의 중심 서사다. 세 행으로 나눈 이유는 한 행에 세 가지를
-- 담으면 모델이 그중 하나만 골라 말하고 나머지 둘은 영영 안 나오기 때문이다.
('40000000-0000-4000-8000-000000000001', :'senior_id'::uuid, 'LIFE_EVENT',
 '김순자는 국민학교에서 30년간 아이들을 가르쳤고, 그중에서도 가을 운동회 준비하던 때를 제일 즐거워했다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['국민학교','교사','선생님','아이들','운동회','학교'], 5, NULL, NULL, NULL, 'PENDING'),

('40000000-0000-4000-8000-000000000002', :'senior_id'::uuid, 'LIFE_EVENT',
 '첫 부임지가 시골 분교였다. 겨울이면 교실 난로 위에 아이들 도시락을 올려 데워 주었다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['분교','첫 부임','난로','도시락','겨울','교실'], 5, NULL, NULL, NULL, 'PENDING'),

('40000000-0000-4000-8000-000000000003', :'senior_id'::uuid, 'LIFE_EVENT',
 '졸업식 날 제자들이 모아 준 손편지 묶음을 아직도 장롱에 간직하고 있다.',
 'USER_CONFIRMED', 'ACTIVE', 'PRIVATE',
 ARRAY['졸업식','제자','편지','장롱','간직'], 5, NULL, NULL, NULL, 'PENDING'),

-- 지금도 하는 것 — 회상과 오늘을 잇는 다리다. 기존 HOBBY 행("화분 가꾸는 것을
-- 좋아한다")보다 구체적이라, 같은 화제에서 이쪽이 먼저 뽑힌다.
('40000000-0000-4000-8000-000000000004', :'senior_id'::uuid, 'HOBBY',
 '베란다에서 화분을 가꾼다. 군자란과 제라늄을 특히 아껴서 물 주는 날을 따로 센다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['화분','베란다','군자란','제라늄','꽃','물 주기'], 5, NULL, NULL, NULL, 'PENDING'),

('40000000-0000-4000-8000-000000000005', :'senior_id'::uuid, 'HOBBY',
 '트로트를 좋아해서 설거지할 때 라디오를 틀어 놓고 따라 부른다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['트로트','노래','라디오','설거지','흥얼'], 5, NULL, NULL, NULL, 'PENDING'),

-- 가족 — 손자는 기존 memory 에도 있다(중복 3행). 여기서는 '무엇을 하는지'까지
-- 적어서, 로봇이 "손자분 오셨어요?" 대신 "이번 주에도 부침개 부쳐 주셨어요?"를
-- 말할 수 있게 한다.
('40000000-0000-4000-8000-000000000006', :'senior_id'::uuid, 'FAMILY_MEMORY',
 '손자가 주말마다 놀러 오면 부침개를 부쳐 준다. 손자는 김치전을 제일 좋아한다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['손자','주말','부침개','김치전','간식'], 5, NULL, NULL, NULL, 'PENDING'),

('40000000-0000-4000-8000-000000000007', :'senior_id'::uuid, 'FAMILY_MEMORY',
 '아이들이 어릴 적, 여름이면 마당에 평상을 펴고 모깃불을 피워 놓고 옥수수를 쪄 먹었다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['평상','마당','여름','모깃불','옥수수','아이들'], 5, NULL, NULL, NULL, 'PENDING'),

-- 사는 곳 — 날씨·외출 화제와 자연스럽게 붙는다.
('40000000-0000-4000-8000-000000000008', :'senior_id'::uuid, 'LIFE_EVENT',
 '부산 강서구에서 마흔 해 넘게 살았다. 지금 아파트가 선 자리가 예전에는 논밭이었다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['부산','강서구','동네','논밭','아파트','이사'], 5, NULL, NULL, NULL, 'PENDING'),

('40000000-0000-4000-8000-000000000009', :'senior_id'::uuid, 'PREFERENCE',
 '시장 구경을 좋아한다. 예전에는 장날마다 나가서 좌판을 한 바퀴 다 돌아보고 왔다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['시장','장날','좌판','구경','장보기'], 5, NULL, NULL, NULL, 'PENDING'),

('40000000-0000-4000-8000-00000000000a', :'senior_id'::uuid, 'LIFE_EVENT',
 '젊을 때는 재봉틀로 아이들 옷을 직접 지어 입혔다. 명절 전날이면 밤새 박음질을 했다.',
 'USER_CONFIRMED', 'ACTIVE', 'SHARED_WITH_PRIMARY',
 ARRAY['재봉틀','바느질','옷','명절','박음질'], 5, NULL, NULL, NULL, 'PENDING');

-- ─────────────────────────────────────────────────────────────────────────────
-- 2) 가족 명부 — 회피 목록의 권위
--
-- ★★ 여기가 이 파일에서 가장 위험한 부분이다. 반드시 읽을 것.
--
--   KnownPerson.isAvoidTarget() 는 `!Boolean.FALSE.equals(isDeceased)` 다.
--   즉 **is_deceased 가 NULL 이면 회피 대상이 된다.** 살아 있는 손자를 무심코
--   NULL 로 등록하면, 로봇은 손자 이야기를 영영 먼저 꺼내지 않는다 — 위 6번
--   씨앗이 통째로 죽는다. 살아 있는 사람은 반드시 FALSE 를 명시한다.
--
--   그리고 known_person 에 행이 하나라도 생기는 순간, 이 표가 회피 목록의 유일한
--   권위가 된다(ConversationContextService.extractAvoidTopics). jsonb 쪽
--   conversation_preferences.avoid_topics 폴백은 그때부터 읽히지 않는다.
--   지금 그 jsonb 에는 avoid_topics 가 없으므로 잃는 것은 없다.
--
--   회피 문구는 사실이 아니라 '금지'로 나간다("○○ 이야기는 로봇이 먼저 꺼내지
--   않습니다"). deceased_note 는 프롬프트에 절대 실리지 않는다 — 사실로 주면
--   모델이 그것을 화제로 삼기 때문이다(CLAUDE.md §8, §17.5).
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO known_person (
    id, senior_id, guardian_user_id, display_name, relationship,
    is_deceased, deceased_note, lives_with, contact_frequency,
    last_mentioned_at, created_at, updated_at
) VALUES
-- 살아 있는 가족은 FALSE 를 명시한다. 이 세 줄이 위 회상 씨앗을 지킨다.
('41000000-0000-4000-8000-000000000001', :'senior_id'::uuid, NULL,
 '손자', '손자', FALSE, NULL, FALSE, 'WEEKLY', NULL,
 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

('41000000-0000-4000-8000-000000000002', :'senior_id'::uuid,
 '10000000-0000-4000-8000-000000000002', '우동균', '아들', FALSE, NULL, FALSE, 'WEEKLY',
 NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

('41000000-0000-4000-8000-000000000003', :'senior_id'::uuid,
 '10000000-0000-4000-8000-000000000003', '차서영', '며느리', FALSE, NULL, FALSE, 'MONTHLY',
 NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- ★ 실제 회피 대상은 사람만 안다 — 사별·절연·투병 중인 가족 등.
--   이 페르소나에는 확립된 사별 사실이 없어서 **일부러 비워 두었다.** 없는 사별을
--   지어내면 로봇이 그 사람을 피하는지 확인할 길도 없이 데이터만 오염된다.
--   알게 되면 아래 형태로 한 줄 추가한다. is_deceased 를 TRUE 로 두는 것만으로
--   회피 대상이 되고, 문구는 백엔드가 만든다.
--
-- INSERT INTO known_person (
--     id, senior_id, guardian_user_id, display_name, relationship,
--     is_deceased, deceased_note, lives_with, contact_frequency,
--     last_mentioned_at, created_at, updated_at
-- ) VALUES
-- ('41000000-0000-4000-8000-000000000009', :'senior_id'::uuid, NULL,
--  '남편', '배우자', TRUE, '2024년 봄에 사별. 어르신이 먼저 꺼내면 듣기만 한다.',
--  FALSE, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

COMMIT;

-- 확인 --------------------------------------------------------------------
--   embedding_status 는 PENDING 으로 들어간다. 5분 안에 동기화 잡이 SYNCED 로
--   바꾼다(로그: "embedding sync: N memories ... indexed"). SYNCED 가 되기
--   전까지 이 씨앗들은 의미 검색에 걸리지 않는다 — 키워드로만 걸린다.
SELECT memory_type, importance, embedding_status, left(content, 34) AS content
  FROM memory WHERE senior_id = :'senior_id'::uuid AND importance = 5
 ORDER BY memory_type, content;

SELECT display_name, relationship, is_deceased,
       (NOT COALESCE(is_deceased, TRUE)) AS "회피대상아님"
  FROM known_person WHERE senior_id = :'senior_id'::uuid ORDER BY display_name;
