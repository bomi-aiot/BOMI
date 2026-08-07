\set ON_ERROR_STOP on
\pset pager off

SELECT current_database() AS database_name, current_schema() AS default_schema;

SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('hospital', 'drug_permit', 'pharmacy')
ORDER BY tablename;

SELECT dataset, actual_rows, expected_rows, actual_rows = expected_rows AS matches
FROM (
    SELECT
        'hospital'::text AS dataset,
        count(*) AS actual_rows,
        79777::bigint AS expected_rows
    FROM public.hospital

    UNION ALL

    SELECT
        'drug_permit',
        count(*),
        42952::bigint
    FROM public.drug_permit

    UNION ALL

    SELECT
        'pharmacy',
        count(*),
        25759::bigint
    FROM public.pharmacy
) counts
ORDER BY dataset;

SELECT ykiho, yadm_nm, cl_cd, post_no
FROM public.hospital
WHERE cl_cd = '01'
ORDER BY ykiho
LIMIT 3;

SELECT ykiho, yadm_nm, post_no
FROM public.pharmacy
WHERE post_no LIKE '0%'
ORDER BY ykiho
LIMIT 3;

SELECT item_seq, item_name, item_permit_date, bizrno
FROM public.drug_permit
ORDER BY item_seq
LIMIT 3;

SELECT
    (SELECT count(*) FROM public.hospital WHERE ykiho IS NULL OR ykiho = '') AS hospital_blank_ykiho,
    (SELECT count(*) FROM public.pharmacy WHERE ykiho IS NULL OR ykiho = '') AS pharmacy_blank_ykiho,
    (SELECT count(*) FROM public.drug_permit WHERE item_seq IS NULL OR item_seq = '') AS drug_blank_item_seq;
