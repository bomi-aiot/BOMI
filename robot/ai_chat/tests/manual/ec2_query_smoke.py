"""EC2 PostgreSQL 의약품 유사 검색 결과를 직접 점검한다."""

import difflib
import unicodedata


def debug_candidates(
    input_value: str,
    *,
    threshold: float = 0.05,
    candidate_count: int = 20,
) -> None:
    import psycopg2.extras

    from bomi_ai_chat.db.medical_repository import _get_conn

    query = """
        SELECT item_name, word_similarity(%s, item_name) AS score
        FROM drug_permit
        WHERE word_similarity(%s, item_name) > %s
        ORDER BY score DESC
        LIMIT %s
    """
    with _get_conn() as connection:
        with connection.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cursor:
            cursor.execute(
                query,
                (input_value, input_value, threshold, candidate_count),
            )
            rows = cursor.fetchall()

    print(f"\n--- {input_value!r} 1단계(pg_trgm) 후보 {len(rows)}개 ---")
    for row in rows:
        print(f"  {row['item_name']}  (trgm score: {row['score']:.4f})")

    input_length = len(input_value)
    scored = []
    for row in rows:
        candidate = row["item_name"]
        prefix = candidate[: input_length + 2]
        normalized_input = unicodedata.normalize("NFD", input_value)
        normalized_candidate = unicodedata.normalize("NFD", prefix)
        ratio = difflib.SequenceMatcher(
            None,
            normalized_input,
            normalized_candidate,
        ).ratio()
        scored.append((candidate, ratio))

    print(f"--- {input_value!r} 2단계(자모 비교) 재정렬 ---")
    for candidate, score in sorted(scored, key=lambda item: item[1], reverse=True)[:5]:
        print(f"  {candidate}  (jamo score: {score:.4f})")


def main() -> None:
    from bomi_ai_chat.config import Settings
    from bomi_ai_chat.db.medical_repository import (
        find_closest_value,
        find_drug_info,
    )

    Settings.from_env().validate_database()
    debug_candidates("타이레놀")
    debug_candidates("타이네롤")

    print("\n=== find_closest_value 결과 ===")
    print(
        "타이레놀 보정:",
        find_closest_value("drug_permit", "item_name", "타이레놀"),
    )
    print(
        "타이네롤 보정:",
        find_closest_value("drug_permit", "item_name", "타이네롤"),
    )
    print("\n=== find_drug_info 결과 ===")
    print("타이레놀 조회:", find_drug_info("타이레놀"))
    print("타이네롤 조회:", find_drug_info("타이네롤"))


if __name__ == "__main__":
    main()
