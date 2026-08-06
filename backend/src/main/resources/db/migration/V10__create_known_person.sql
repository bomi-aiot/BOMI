-- V10 : known_person 테이블을 신설한다 (S15P11E102-260)
--
-- 무엇이 문제였는가
--   회피 대상("돌아가신 배우자 이야기는 하지 말아 주세요")을 넣을 곳이
--   app_user.conversation_preferences 라는 자유 형식 jsonb 의 avoid_topics 키
--   하나뿐이었다. 그런데 이 키를 채우는 코드가 저장소 어디에도 없었고("남편 사망"
--   같은 문자열은 테스트에만 존재했다), 컬럼정의서는 이 칸에 "가족 사실 금지"라고
--   못박아 두었는데 실제로는 가족 사실이 들어가는 모순도 있었다. 결과: 가장
--   위험한 안전장치가 한 번도 작동한 적이 없었다.
--
-- 왜 구조화된 표인가
--   "이 사람이 누구이고 지금 어떤 상태인가"를 결정론적으로 걸러야 한다
--   (CLAUDE.md §8, §17.5). 자유 문자열로는 "민수는 잘 있대요?" 같은 자연스러운
--   이어짐(생존 가족)과 "절대 먼저 꺼내지 않을 사람"(사망·모름)을 코드가 구분할
--   방법이 없다. 이름·관계·생존 여부를 컬럼으로 분리하면 그 구분이 가능해진다.
--
-- 참고: CLAUDE.md §8(회피는 결정론적으로, memory 로 보내지 않는다), §19(DB 작업 항목)
CREATE TABLE known_person (
    id                  uuid          NOT NULL,
    senior_id           uuid          NOT NULL,

    -- 이 사람을 등록한 보호자. NULL 허용 — 온보딩 등 보호자 앱을 거치지 않고
    -- 채워질 수도 있는 경로를 남겨 둔다. 물리 FK 가 아니라 논리 참조로 둔다
    -- (CareRecord.recipientGuardianId 와 같은 관례).
    guardian_user_id    uuid,

    display_name        varchar(100)  NOT NULL,

    -- "배우자"·"아들"·"친구" 같은 자유 텍스트. 코드 사전을 지금 확정하기엔
    -- 가족 구성이 너무 다양해서, care_record.record_type 처럼 넓게 열어 둔다.
    relationship         varchar(50),

    -- ── 생존 여부: NULL 이 '모름'이다 ─────────────────────────────────────
    -- 세 값을 모두 구분해야 한다.
    --   TRUE  : 돌아가셨다 -> 먼저 꺼내지 않는다.
    --   FALSE : 살아 계시다 -> 자연스러운 이어짐에 쓸 수 있다("민수는 잘 있대요?").
    --   NULL  : 모른다 -> 이 완료 조건이 명시적으로 요구하는 대로, TRUE 와 똑같이
    --           먼저 꺼내지 않는다. "모르니까 일단 언급해도 된다"는 이 제품에서
    --           가장 위험한 실수 중 하나로 이어진다.
    is_deceased          boolean,

    -- 보호자가 남기는 맥락 메모(예: "작년 겨울에 돌아가셨습니다"). 프롬프트에는
    -- 절대 그대로 노출하지 않는다 — 회피 문구는 정보가 아니라 금지문으로만
    -- 전달한다(ConversationContextService 참고). 이 칸은 보호자 앱 화면과
    -- 다른 보호자를 위한 내부 메모일 뿐이다.
    deceased_note         varchar(500),

    -- 함께 사는지. NULL 은 '모름', FALSE 는 '따로 산다' — 0/1 이 아니라 boolean
    -- 이므로 daily_activity_metric 과 같은 "모르는 것과 아니오는 다르다" 원칙이
    -- 여기도 적용된다.
    lives_with            boolean,

    -- "매일"·"주 1회"처럼 자유 텍스트. 코드 사전화는 이후 필요할 때.
    contact_frequency     varchar(50),

    -- 로봇이 이 사람을 마지막으로 언급/거론한 시각. 이 티켓은 컬럼만 만든다 —
    -- 자동 갱신은 로봇 쪽 자연스러운 이어짐 기능(§17.2)이 붙을 때의 몫이다.
    last_mentioned_at     timestamptz,

    created_at            timestamptz   NOT NULL,
    updated_at            timestamptz   NOT NULL,

    CONSTRAINT pk_known_person PRIMARY KEY (id)
);

-- 문맥 조립이 매 턴 "이 어르신의 회피 대상"을 조회한다. senior_id 단독 인덱스로
-- 충분하다 — 한 어르신의 명부 크기가 수십 명을 넘지 않는다.
CREATE INDEX idx_known_person_senior ON known_person (senior_id);
