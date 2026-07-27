\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    hospital_count bigint;
    drug_permit_count bigint;
    pharmacy_count bigint;
BEGIN
    IF to_regnamespace('public_data_raw') IS NOT NULL THEN
        RAISE EXCEPTION 'Target schema public_data_raw already exists; refusing to overwrite it';
    END IF;

    IF to_regnamespace('public_data_raw_load_20260727') IS NULL THEN
        RAISE EXCEPTION 'Stage schema public_data_raw_load_20260727 does not exist';
    END IF;

    SELECT count(*) INTO hospital_count
    FROM public_data_raw_load_20260727.hospital;

    SELECT count(*) INTO drug_permit_count
    FROM public_data_raw_load_20260727.drug_permit;

    SELECT count(*) INTO pharmacy_count
    FROM public_data_raw_load_20260727.pharmacy;

    IF hospital_count <> 79777 THEN
        RAISE EXCEPTION 'Hospital row count mismatch: expected 79777, got %', hospital_count;
    END IF;

    IF drug_permit_count <> 42952 THEN
        RAISE EXCEPTION 'Drug permit row count mismatch: expected 42952, got %', drug_permit_count;
    END IF;

    IF pharmacy_count <> 25759 THEN
        RAISE EXCEPTION 'Pharmacy row count mismatch: expected 25759, got %', pharmacy_count;
    END IF;
END
$$;

CREATE INDEX hospital_ykiho_idx
    ON public_data_raw_load_20260727.hospital (ykiho);

CREATE INDEX drug_permit_item_seq_idx
    ON public_data_raw_load_20260727.drug_permit (item_seq);

CREATE INDEX pharmacy_ykiho_idx
    ON public_data_raw_load_20260727.pharmacy (ykiho);

ALTER SCHEMA public_data_raw_load_20260727
    RENAME TO public_data_raw;

COMMIT;

ANALYZE public_data_raw.hospital;
ANALYZE public_data_raw.drug_permit;
ANALYZE public_data_raw.pharmacy;
