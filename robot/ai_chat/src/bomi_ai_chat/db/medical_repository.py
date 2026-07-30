# robot/ai_chat/src/bomi_ai_chat/db/medical_repository.py
"""
DB 조회 전담 모듈.
로컬 테스트: springboot_local DB의 hospital/pharmacy/drug_permit 테이블 사용.
EC2 이전 시 DATABASE_URL만 바꾸면 됨 (쿼리/컬럼명은 백엔드와 스키마 확정 필요).
"""
import difflib
import unicodedata

import psycopg2
import psycopg2.extras

from bomi_ai_chat.config import get_settings
from bomi_ai_chat.db.ssh_tunnel import get_local_port


def _get_conn():
    settings = get_settings()
    settings.validate_database()

    if settings.db_connection_mode == "direct":
        if settings.database_url:
            return psycopg2.connect(
                settings.database_url,
                client_encoding="utf-8",
            )
        return psycopg2.connect(
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            client_encoding="utf-8",
        )

    port = get_local_port()
    return psycopg2.connect(
        host="localhost",
        port=port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        client_encoding="utf-8",
    )


def _jamo_similarity(a, b):
    """
    문자열을 초성/중성/종성 단위로 분해해서 유사도를 계산한다.
    음절 단위 비교(difflib 그대로)보다 오타/발음 혼동(예: '레'-'네')에 강하다.
    """
    jamo_a = unicodedata.normalize("NFD", a)
    jamo_b = unicodedata.normalize("NFD", b)
    return difflib.SequenceMatcher(None, jamo_a, jamo_b).ratio()


def find_closest_value(table, column, input_value, threshold=0.05,
                        candidate_count=20, high_confidence=0.7):
    """
    입력값(오타 가능성이 있는 사용자 발화)과 가장 비슷한 실제 DB 값을 찾는다.

    1단계 (DB, pg_trgm word_similarity): "명백히 무관한 데이터"만 걸러내는
       용도로 threshold를 낮게 잡고, candidate_count개(기본 20개)를 넉넉히 뽑는다.

    2단계 (파이썬, 자모 분해): 1단계 후보들을 초성/중성/종성 단위로 쪼개
       input_value와 다시 비교해 정밀하게 재정렬한다.

    3단계 (확신도 체크): 1등 점수가 high_confidence 이상이면 확정하고,
       미만이면 무조건 None을 반환한다. 이전에는 1등-2등 점수 차이(margin)로
       판단했으나, 이 방식은 "1단계 후보 전체가 오답이어도 그 안에서
       1등이 2등보다 크게 앞서면 통과시켜버리는" 결함이 있었다
       (실제 사례: '타이네롤' 입력 시 진짜 정답 '타이레놀'은 후보에도
       못 들었는데, 오답들 사이의 상대적 우위만으로 확정돼버림).
       그래서 상대 비교 대신 절대 점수 하나만으로 판단한다.

    table, column은 항상 코드 내부에서 고정된 값만 전달할 것
    (사용자 입력을 직접 넣지 말 것 — SQL 인젝션 방지).

    비교 시 입력값과 후보 문자열 모두 공백을 제거한 뒤 비교한다(STT 인식
    과정에서 공백이 엉뚱하게 끼어들 수 있어서). 단, 실제로 반환하는 값은
    DB에 저장된 원본 문자열 그대로다 — 정규화는 비교 목적으로만 쓰인다.
    """
    normalized_input = "".join(input_value.split())

    query = f"""
        SELECT {column}, word_similarity(%s, {column}) AS score
        FROM {table}
        WHERE word_similarity(%s, {column}) > %s
        ORDER BY score DESC
        LIMIT %s
    """
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (normalized_input, normalized_input, threshold, candidate_count))
            rows = cur.fetchall()

    if not rows:
        return None

    input_len = len(normalized_input)
    scored = []
    for row in rows:
        candidate = row[column]
        normalized_candidate = "".join(candidate.split())
        candidate_prefix = normalized_candidate[: input_len + 2]
        jamo_score = _jamo_similarity(normalized_input, candidate_prefix)
        scored.append((candidate, jamo_score))  # candidate는 원본 유지(반환용)
    scored.sort(key=lambda x: x[1], reverse=True)

    top_candidate, top_score = scored[0]

    if top_score >= high_confidence:
        return top_candidate
    return None


def _multi_token_ilike(column, value):
    """
    지역명처럼 여러 단어가 공백으로 붙어 들어오는 값(예: '부산 서면')을
    하나의 연속 문자열로 통째로 ILIKE 하면 실패하기 쉽다 — 실제 주소는
    '부산광역시 부산진구 서면문화로 8'처럼 단어들이 붙어있지 않기 때문이다.
    그래서 공백 기준으로 토큰을 쪼개, "각 토큰이 어딘가에는 다 포함되어야
    한다(AND, 순서/인접 무관)" 조건으로 바꾼다.

    반환값: (SQL 조건절 문자열, 파라미터 리스트)
    """
    tokens = [t for t in value.split() if t]
    if not tokens:
        return "TRUE", []
    conditions = " AND ".join([f"{column} ILIKE %s" for _ in tokens])
    params = [f"%{t}%" for t in tokens]
    return conditions, params


def find_hospitals(name=None, region=None, department=None, limit=5):
    """
    department: 실제로는 hospital 테이블에 진료과 컬럼이 없어서
    cl_cd_nm(종별 코드명, 예: 종합병원/의원/병원 등)으로 대체 필터링.
    region: 여러 단어(예: '부산 서면')가 들어올 수 있어 토큰별로 나눠 매칭한다.

    name에는 자모 유사도 보정을 적용하지 않는다. 의약품과 달리 병원/약국
    이름은 "정식 명칭 vs 줄임말"(예: '서울대병원' vs '서울대학교병원')
    차이가 오타보다 흔한데, 이 경우 문자열이 비슷한 완전히 다른 기관이
    실재할 수 있어(예: '서울대효병원') 잘못된 시설을 확신 있게 안내할
    위험이 크다. 위치 정보 오안내는 실제 안전 문제로 이어질 수 있어,
    정확/부분 일치가 없으면 "찾을 수 없음"으로 정직하게 답하는 쪽을 택한다.
    """
    query = "SELECT DISTINCT yadm_nm, addr, cl_cd_nm FROM hospital WHERE 1=1"
    params = []
    if name:
        query += " AND yadm_nm ILIKE %s"
        params.append(f"%{name}%")
    if region:
        condition, region_params = _multi_token_ilike("addr", region)
        query += f" AND ({condition})"
        params.extend(region_params)
    if department:
        query += " AND cl_cd_nm ILIKE %s"
        params.append(f"%{department}%")
    query += " LIMIT %s"
    params.append(limit)

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def find_pharmacies(name=None, region=None, limit=5):
    """
    region: 여러 단어(예: '부산 서면')가 들어올 수 있어 토큰별로 나눠 매칭한다.
    name에는 자모 유사도 보정을 적용하지 않는다 (이유는 find_hospitals 참고).
    """
    query = "SELECT yadm_nm, addr, telno FROM pharmacy WHERE 1=1"
    params = []
    if name:
        query += " AND yadm_nm ILIKE %s"
        params.append(f"%{name}%")
    if region:
        condition, region_params = _multi_token_ilike("addr", region)
        query += f" AND ({condition})"
        params.extend(region_params)
    query += " LIMIT %s"
    params.append(limit)

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def find_drug_info(item_name, limit=3):
    """
    drug_permit 테이블에는 제형/복용법/보관방법/전문-일반 구분 컬럼이 없음.
    현재 스키마에 실제 존재하는 컬럼만 조회.

    반환값: {"results": [...], "match_type": "exact" | "corrected" | None}
    - "exact": 사용자가 말한 이름과 (공백 무시하고) 정확히 일치하는 제품을 찾음
    - "corrected": 정확히 일치하는 게 없어서 find_closest_value로 자모 유사도
      보정을 거쳐 찾은 것. STT가 첫 글자부터 잘못 알아듣는 경우(예: '타이레놀'을
      '하이레놀'로 인식) 보정이 완전히 다른 약(예: 전문의약품/주사제)으로
      튈 수 있는 게 실제로 관측되어, 이 경우는 상세 정보를 바로 주지 않고
      호출부에서 반드시 확인 질문을 거치도록 구분해서 표시한다. 잘못된
      약 정보(성분/제형/전문·일반 구분 등)를 확신 있게 전달하는 건 실제
      위해로 이어질 수 있는 안전 문제이기 때문이다.
    - None: 아무것도 못 찾음
    """
    normalized_input = "".join(item_name.split())

    # 1단계: 공백만 무시하고 정확히 일치하는 제품이 있는지 먼저 확인
    exact_query = """
        SELECT item_name, entp_name, item_permit_date, item_ingr_name, prduct_type
        FROM drug_permit
        WHERE regexp_replace(item_name, '\\s+', '', 'g') = %s
        LIMIT %s
    """
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(exact_query, (normalized_input, limit))
            exact_rows = cur.fetchall()

    if exact_rows:
        return {"results": exact_rows, "match_type": "exact"}

    # 2단계: 정확히 일치하는 게 없으면 자모 유사도 보정 시도
    corrected_name = find_closest_value("drug_permit", "item_name", item_name)
    if not corrected_name:
        return {"results": [], "match_type": None}

    corrected_query = """
        SELECT item_name, entp_name, item_permit_date, item_ingr_name, prduct_type
        FROM drug_permit
        WHERE item_name = %s
        LIMIT %s
    """
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(corrected_query, (corrected_name, limit))
            rows = cur.fetchall()

    return {"results": rows, "match_type": "corrected"}
