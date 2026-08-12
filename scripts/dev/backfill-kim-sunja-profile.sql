-- 김순자 프로필의 빈 칸 채우기 (이미 seed 된 DB 용)
--
-- 왜 seed-kim-sunja.sql 로 안 되는가
--   그 스크립트는 대상 13개 테이블 중 하나라도 비어 있지 않으면 통째로 중단한다.
--   이미 김순자 가구가 들어 있는 DB(시연/리허설 DB)에서는 절대 실행되지 않으므로,
--   V2·V9·V11·V17 로 나중에 늘어난 nullable 컬럼은 그 DB에서 영원히 NULL 로 남는다.
--   이 파일이 그 차이만 메운다.
--
-- 값의 근거는 seed-kim-sunja.sql 의 같은 컬럼 주석과 동일하다. 여기서 한 벌 더
-- 설명하지 않는다 — 두 곳에 적으면 갈라진다.
--
-- 안전
--   * UPDATE 대상은 김순자 UUID 한 행뿐이다.
--   * COALESCE 로 감싸 **비어 있는 칸만** 채운다. 사람이 이미 손으로 넣어 둔 값이
--     있으면 그대로 둔다 — 이 스크립트를 두 번 돌려도 결과가 같다.
--   * 실측·문진으로 확인된 값이 따로 있으면 이 파일을 고쳐서 쓴다. 여기 값은
--     "모르는 채로 두는 것보다 나은 개발용 기본값"이지 김순자 본인의 사실이 아니다.

BEGIN;

UPDATE app_user
SET
    birth_date         = COALESCE(birth_date, DATE '1946-03-12'),
    home_address       = COALESCE(home_address, '부산광역시 강서구'),
    home_latitude      = COALESCE(home_latitude, 35.094333),
    home_longitude     = COALESCE(home_longitude, 128.855167),
    wake_time          = COALESCE(wake_time, TIME '07:00'),
    sleep_time         = COALESCE(sleep_time, TIME '22:00'),
    chronic_pain_area  = COALESCE(chronic_pain_area, '양쪽 무릎, 허리'),
    preferred_hospital = COALESCE(preferred_hospital, '부산 강서구보건소'),
    updated_at         = CURRENT_TIMESTAMP
WHERE id = '10000000-0000-4000-8000-000000000001'
  AND user_type = 'SENIOR';

COMMIT;

-- 실행 후 확인 — 아래 8칸에 NULL 이 남아 있으면 안 된다.
SELECT name,
       birth_date,
       home_address,
       home_latitude,
       home_longitude,
       wake_time,
       sleep_time,
       chronic_pain_area,
       preferred_hospital
FROM app_user
WHERE id = '10000000-0000-4000-8000-000000000001';
