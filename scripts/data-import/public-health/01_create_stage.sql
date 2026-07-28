\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
    IF current_database() = 'bomi' THEN
        RAISE EXCEPTION 'Refusing to create public-health staging tables in the bomi database';
    END IF;

    IF to_regclass('public.hospital') IS NOT NULL
        OR to_regclass('public.drug_permit') IS NOT NULL
        OR to_regclass('public.pharmacy') IS NOT NULL THEN
        RAISE EXCEPTION 'One or more target tables already exist in the public schema';
    END IF;

    IF to_regnamespace('public_data_raw_load_20260727') IS NOT NULL THEN
        RAISE EXCEPTION 'Stage schema public_data_raw_load_20260727 already exists; inspect it before retrying';
    END IF;
END
$$;

CREATE SCHEMA public_data_raw_load_20260727;

COMMENT ON SCHEMA public_data_raw_load_20260727 IS
    'One-time staging schema before promotion into the public schema';

CREATE TABLE public_data_raw_load_20260727.hospital (
    addr text,
    cl_cd text,
    cl_cd_nm text,
    cmdc_gdr_cnt text,
    cmdc_intn_cnt text,
    cmdc_resdnt_cnt text,
    cmdc_sdr_cnt text,
    dety_gdr_cnt text,
    dety_intn_cnt text,
    dety_resdnt_cnt text,
    dety_sdr_cnt text,
    dr_tot_cnt text,
    emdong_nm text,
    estb_dd text,
    hosp_url text,
    mdept_gdr_cnt text,
    mdept_intn_cnt text,
    mdept_resdnt_cnt text,
    mdept_sdr_cnt text,
    pnurs_cnt text,
    post_no text,
    sggu_cd text,
    sggu_cd_nm text,
    sido_cd text,
    sido_cd_nm text,
    telno text,
    x_pos text,
    y_pos text,
    yadm_nm text,
    ykiho text
);

CREATE TABLE public_data_raw_load_20260727.drug_permit (
    item_seq text,
    item_name text,
    item_eng_name text,
    entp_name text,
    entp_eng_name text,
    entp_seq text,
    entp_no text,
    item_permit_date text,
    induty text,
    prdlst_stdr_code text,
    spclty_pblc text,
    prduct_type text,
    prduct_prmisn_no text,
    item_ingr_name text,
    item_ingr_cnt text,
    big_prdt_img_url text,
    permit_kind_code text,
    cancel_date text,
    cancel_name text,
    edi_code text,
    bizrno text
);

CREATE TABLE public_data_raw_load_20260727.pharmacy (
    addr text,
    cl_cd text,
    cl_cd_nm text,
    emdong_nm text,
    estb_dd text,
    post_no text,
    sggu_cd text,
    sggu_cd_nm text,
    sido_cd text,
    sido_cd_nm text,
    telno text,
    x_pos text,
    y_pos text,
    yadm_nm text,
    ykiho text
);

COMMIT;
