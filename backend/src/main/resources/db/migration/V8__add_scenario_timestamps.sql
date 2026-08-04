-- V8 : scenario 에 created_at / updated_at 추가 (S15P11E102-283)
--
-- 무엇이 문제였나
--   scenario 에 시각 컬럼이 하나도 없었다. "이 어르신에게 방금 같은 시나리오가
--   돌지 않았나"를 물을 방법이 없었다.
--
-- 왜 지금 필요한가
--   온습도(AMBIENT_ENVIRONMENT_OBSERVED)는 문 열림과 달리 연속 신호다. 더운 방은
--   5분 뒤에도 덥다. 시각 없이는 "이상 지속 = 시나리오 무한 생성"을 막을 수 없다.
--   쿨다운 판정(최근 N분 내 동종 시나리오 완료 여부)이 updated_at 을 읽는다.
--
-- updated_at 의 의미
--   마지막 상태 전이 시각. 시나리오는 상태가 바뀔 때만 저장되므로, 터미널 상태
--   행의 updated_at 은 곧 "그 시나리오가 끝난 시각"이다. 쿨다운은 이 값을 쓴다.
--
-- 백필을 now() 로 하는 이유 (V7 의 "지어내지 않는다"와 다른 선택)
--   care_record 는 보호자에게 보이는 이력이라 모르는 시각을 지어내면 안 됐다.
--   scenario 의 시각은 사람에게 보이지 않고 쿨다운 판정에만 쓰인다. 기존 행은
--   개발 데이터뿐이고, now() 백필의 최악 효과는 배포 직후 30분간 쿨다운이 한 번
--   더 걸리는 것이다. NULL 을 남겨 모든 질의에 NULL 분기를 얹는 것보다 싸다.

ALTER TABLE scenario ADD COLUMN created_at timestamptz;
ALTER TABLE scenario ADD COLUMN updated_at timestamptz;

UPDATE scenario SET created_at = now(), updated_at = now()
WHERE created_at IS NULL;

ALTER TABLE scenario ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE scenario ALTER COLUMN updated_at SET NOT NULL;

COMMENT ON COLUMN scenario.created_at IS '시나리오 생성 시각. S15P11E102-283';
COMMENT ON COLUMN scenario.updated_at IS
    '마지막 상태 전이 시각. 터미널 상태 행에서는 종료 시각을 뜻하며 쿨다운 판정이 읽는다. S15P11E102-283';

-- 활성 시나리오 존재 확인: WHERE senior_id = ? AND final_status IN (...)
CREATE INDEX ix_scenario_senior_status
    ON scenario (senior_id, final_status);

-- 쿨다운 판정: WHERE senior_id = ? AND scenario_type = ? AND final_status = ? AND updated_at > ?
-- 범위 조건(updated_at)은 마지막 컬럼에서만 인덱스를 탄다 (V7 인덱스 주석과 같은 원칙).
CREATE INDEX ix_scenario_senior_type_status_updated
    ON scenario (senior_id, scenario_type, final_status, updated_at);
