\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    hospital_count bigint;
    drug_permit_count bigint;
    pharmacy_count bigint;
BEGIN
    IF current_database() = 'bomi' THEN
        RAISE EXCEPTION 'Refusing to promote public-health tables in the bomi database';
    END IF;

    IF to_regclass('public.hospital') IS NOT NULL
        OR to_regclass('public.drug_permit') IS NOT NULL
        OR to_regclass('public.pharmacy') IS NOT NULL THEN
        RAISE EXCEPTION 'One or more target tables already exist in the public schema';
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

ALTER TABLE public_data_raw_load_20260727.hospital
    SET SCHEMA public;

ALTER TABLE public_data_raw_load_20260727.drug_permit
    SET SCHEMA public;

ALTER TABLE public_data_raw_load_20260727.pharmacy
    SET SCHEMA public;

DROP SCHEMA public_data_raw_load_20260727;

COMMIT;

ANALYZE public.hospital;
ANALYZE public.drug_permit;
ANALYZE public.pharmacy;
