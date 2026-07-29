import unicodedata, difflib
from db.medical_repository import _get_conn, find_closest_value, find_drug_info
import psycopg2.extras

def debug_candidates(input_value, table="drug_permit", column="item_name",
                      threshold=0.05, candidate_count=20):
    query = f"""
        SELECT {column}, word_similarity(%s, {column}) AS score
        FROM {table}
        WHERE word_similarity(%s, {column}) > %s
        ORDER BY score DESC
        LIMIT %s
    """
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (input_value, input_value, threshold, candidate_count))
            rows = cur.fetchall()

    print(f"\n--- '{input_value}' 1단계(pg_trgm) 후보 {len(rows)}개 ---")
    for r in rows:
        print(f"  {r[column]}  (trgm score: {r['score']:.4f})")

    input_len = len(input_value)
    scored = []
    for row in rows:
        candidate = row[column]
        prefix = candidate[: input_len + 2]
        jamo_a = unicodedata.normalize("NFD", input_value)
        jamo_b = unicodedata.normalize("NFD", prefix)
        ratio = difflib.SequenceMatcher(None, jamo_a, jamo_b).ratio()
        scored.append((candidate, ratio))
    scored.sort(key=lambda x: x[1], reverse=True)

    print(f"--- '{input_value}' 2단계(자모 비교) 재정렬 ---")
    for c, s in scored[:5]:
        print(f"  {c}  (jamo score: {s:.4f})")


debug_candidates("타이레놀")   # 정확한 이름
debug_candidates("타이네롤")   # 오타

# --- 실제 find_closest_value / find_drug_info 결과 확인 ---
print("\n=== find_closest_value 결과 ===")
print("타이레놀 보정:", find_closest_value("drug_permit", "item_name", "타이레놀"))
print("타이네롤 보정:", find_closest_value("drug_permit", "item_name", "타이네롤"))

print("\n=== find_drug_info 결과 ===")
print("타이레놀 조회:", find_drug_info("타이레놀"))
print("타이네롤 조회:", find_drug_info("타이네롤"))
