-- V5 : 임베딩 동기화 부기 컬럼 (외부 벡터 스토어용)
--
-- ★ pgvector 를 쓰지 않는다. 임베딩 벡터는 이 DB 에 저장되지 않는다.
--
-- 왜 VECTOR 컬럼이 아닌가 (측정된 사실)
--   Upstage solar-embedding-1-large(query/passage)의 출력은 4096차원이다.
--   pgvector 0.8.5 가 인덱싱할 수 있는 상한은 vector 2,000 / halfvec 4,000 차원이다.
--   즉 4096차원은 halfvec 으로도 인덱스를 만들 수 없고, 남는 선택지는 인덱스 없는
--   순차 스캔뿐이다. 한국어 품질 때문에 Upstage 를 포기할 수 없다는 판단이므로
--   의미 검색은 외부 벡터 스토어(Qdrant)로 옮겼다. → S15P11E102-218
--
-- 이 컬럼들이 없으면 무엇이 깨지나
--   벡터 스토어는 '파생 인덱스'이고 이 DB 가 권위다. 그런데 파생물이 유실되거나
--   모델이 바뀌면, 무엇을 다시 임베딩해야 하는지 알 방법이 있어야 한다. 이 세 컬럼이
--   그 유일한 단서다. 없으면 복구는 "전체 재색인"밖에 없고, 부분 실패를 감지할 수도 없다.
--
-- 참고: CLAUDE.md §5(소유권), §8(RAG 경계), §18(임베딩 쓰기는 턴 경로 밖)

-- 장기 기억 ----------------------------------------------------------------
ALTER TABLE memory
    -- PENDING  아직 임베딩되지 않았다(신규 행의 기본값)
    -- SYNCED   벡터 스토어에 반영됐다
    -- STALE    content 가 바뀌었거나 모델이 바뀌어 다시 임베딩해야 한다
    -- FAILED   시도했고 실패했다. 재시도 대상이며 조용히 사라지지 않는다
    --
    -- NOT NULL DEFAULT 'PENDING' 인 이유: 기존 행들도 아직 임베딩되지 않은 것이 사실이다.
    -- NULL 로 두면 재색인 잡이 "모르는 상태"를 매번 따로 처리해야 한다.
    ADD COLUMN embedding_status    varchar(20) NOT NULL DEFAULT 'PENDING',
    ADD COLUMN embedding_synced_at timestamptz,
    -- 어떤 모델이 그 벡터를 만들었는가. 모델을 바꾸면 기존 벡터는 전부 무효다.
    -- 벡터 공간이 다르면 유사도 값이 아무 의미가 없고, 이 실패는 예외 없이 조용히
    -- '검색 품질 하락'으로만 나타난다. 그래서 모델명을 행마다 남긴다.
    ADD COLUMN embedding_model     varchar(100);

-- 대화 요약 ----------------------------------------------------------------
ALTER TABLE conversation_summary
    ADD COLUMN embedding_status    varchar(20) NOT NULL DEFAULT 'PENDING',
    ADD COLUMN embedding_synced_at timestamptz,
    ADD COLUMN embedding_model     varchar(100);

-- 재색인 잡이 "할 일"만 빠르게 찾도록 부분 인덱스를 둔다.
-- 정상 상태(SYNCED)가 대다수가 되므로 전체 인덱스는 낭비다.
CREATE INDEX idx_memory_embedding_resync
    ON memory (embedding_status)
    WHERE embedding_status <> 'SYNCED';

CREATE INDEX idx_conversation_summary_embedding_resync
    ON conversation_summary (embedding_status)
    WHERE embedding_status <> 'SYNCED';
