"""
silver_firm_transport_rate.py
=============================
Example Silver transformation.

Grain: one row per firm contract rate/path (one row per bronze.gtran_rates record).
Reads:  gtran_firm (header) + gtran_rates (rate/path) + gtran_loc (point qty).

==========================  HOW TO ADD A NEW SILVER TABLE  ==========================
Copy this file, then change:
  1. class name + `name`           -> your silver table name
  2. `bronze_sources`              -> the Bronze tables you read
  3. create_table_sql()            -> your CREATE TABLE columns/types
  4. transform_sql()               -> your column mapping + business rules
Keep the two idempotency pieces:
  * CREATE TABLE IF NOT EXISTS  and a UNIQUE natural key
  * INSERT ... SELECT ... ON CONFLICT (natural key) DO UPDATE
====================================================================================
"""

from __future__ import annotations

from ..core.base import SilverTransformation
from ..core.registry import register


@register
class SilverFirmTransportRate(SilverTransformation):
    name = "silver_firm_transport_rate"
    bronze_sources = ["gtran_firm", "gtran_rates", "gtran_loc"]

    # ------------------------------------------------------------------ DDL
    def create_table_sql(self) -> str:
        s = self.silver_schema
        return f"""
        CREATE SCHEMA IF NOT EXISTS {s};

        CREATE TABLE IF NOT EXISTS {s}.firm_transport_rate (
            firm_transport_rate_id  BIGSERIAL PRIMARY KEY,

            -- natural / business keys
            firm_id                 TEXT NOT NULL,
            rate_unique_id          TEXT NOT NULL,
            contract_id             TEXT,

            -- transporter
            tsp_name                TEXT,
            tsp_duns                BIGINT,

            -- shipper & service
            contract_holder_name    TEXT,
            rate_schedule           TEXT,
            service_request_k       TEXT,

            -- contract terms (typed)
            contract_qty_dth        NUMERIC,
            contract_begin_ts       TIMESTAMPTZ,
            contract_end_ts         TIMESTAMPTZ,
            contract_term_days      INTEGER,
            contract_status_code    TEXT,
            contract_status_desc    TEXT,
            is_negotiated_rate      BOOLEAN,

            -- path (receipt -> delivery)
            receipt_loc_code        TEXT,
            receipt_loc_name        TEXT,
            receipt_zone            TEXT,
            receipt_point_qty_dth   NUMERIC,
            delivery_loc_code       TEXT,
            delivery_loc_name       TEXT,
            delivery_zone           TEXT,
            delivery_point_qty_dth  NUMERIC,

            -- rate detail (typed + derived)
            rate_form_type          TEXT,
            rate_form_type_desc     TEXT,
            rate_id                 TEXT,
            rate_charged            NUMERIC,
            max_tariff_rate         NUMERIC,
            total_surcharge         NUMERIC,
            all_in_rate             NUMERIC,
            is_market_based_rate    BOOLEAN,
            has_surcharge           BOOLEAN,

            -- effective windows (typed)
            season_start_date       DATE,
            season_end_date         DATE,
            rate_begin_ts           TIMESTAMPTZ,
            rate_end_ts             TIMESTAMPTZ,
            posted_ts               TIMESTAMPTZ,

            -- lineage back to Bronze
            source_system           TEXT,
            source_api              TEXT,
            pipeline_run_id         TEXT,
            firm_hash_key           TEXT,
            rate_hash_key           TEXT,
            silver_loaded_ts        TIMESTAMPTZ DEFAULT now(),

            CONSTRAINT uq_firm_transport_rate UNIQUE (firm_id, rate_unique_id)
        );
        """

    # ------------------------------------------------------------ transform
    def transform_sql(self) -> str:
        b = self.bronze_schema
        s = self.silver_schema
        # CTEs keep only the latest LOADED version of each Bronze record so the
        # load is robust to re-ingested / amended rows.
        #
        # BUSINESS RULES live here — change casts, joins, and derivations below.
        return f"""
        WITH firm_latest AS (
            SELECT * FROM (
                SELECT f.*, row_number() OVER (
                    PARTITION BY firmid
                    ORDER BY ingestion_timestamp DESC, bronze_row_id DESC) AS rn
                FROM {b}.gtran_firm f
                WHERE ingestion_status = 'LOADED'
            ) x WHERE rn = 1
        ),
        rate_latest AS (
            SELECT * FROM (
                SELECT r.*, row_number() OVER (
                    PARTITION BY firmid, uniqueid
                    ORDER BY ingestion_timestamp DESC, bronze_row_id DESC) AS rn
                FROM {b}.gtran_rates r
                WHERE ingestion_status = 'LOADED'
            ) x WHERE rn = 1
        ),
        loc_latest AS (
            SELECT * FROM (
                SELECT l.*, row_number() OVER (
                    PARTITION BY firmid, loc
                    ORDER BY ingestion_timestamp DESC, bronze_row_id DESC) AS rn
                FROM {b}.gtran_loc l
                WHERE ingestion_status = 'LOADED'
            ) x WHERE rn = 1
        )
        INSERT INTO {s}.firm_transport_rate AS tgt (
            firm_id, rate_unique_id, contract_id,
            tsp_name, tsp_duns,
            contract_holder_name, rate_schedule, service_request_k,
            contract_qty_dth, contract_begin_ts, contract_end_ts, contract_term_days,
            contract_status_code, contract_status_desc, is_negotiated_rate,
            receipt_loc_code, receipt_loc_name, receipt_zone, receipt_point_qty_dth,
            delivery_loc_code, delivery_loc_name, delivery_zone, delivery_point_qty_dth,
            rate_form_type, rate_form_type_desc, rate_id,
            rate_charged, max_tariff_rate, total_surcharge, all_in_rate,
            is_market_based_rate, has_surcharge,
            season_start_date, season_end_date, rate_begin_ts, rate_end_ts, posted_ts,
            source_system, source_api, pipeline_run_id, firm_hash_key, rate_hash_key
        )
        SELECT
            r.firmid,
            r.uniqueid,
            f.id,

            f.tspname,
            NULLIF(f.tspduns, '')::BIGINT,

            f.kholdername,
            f.ratesch,
            f.svcreqk,

            NULLIF(f.kqtyk, '')::NUMERIC,
            NULLIF(f.kbegdatetime, '')::TIMESTAMPTZ,
            NULLIF(f.kenddatetime, '')::TIMESTAMPTZ,
            (NULLIF(f.kenddatetime, '')::TIMESTAMPTZ::DATE
                - NULLIF(f.kbegdatetime, '')::TIMESTAMPTZ::DATE),
            f.kstat,
            f.kstatdesc,
            CASE upper(NULLIF(f.ngtdrateind, '')) WHEN 'Y' THEN TRUE WHEN 'N' THEN FALSE END,

            r.recloc,
            r.reclocname,
            r.recloczn,
            NULLIF(lr.kqtyloc, '')::NUMERIC,
            r.delloc,
            r.dellocname,
            r.delloczn,
            NULLIF(ld.kqtyloc, '')::NUMERIC,

            r.rateformtype,
            r.rateformtypedesc,
            r.rateid,
            NULLIF(r.ratechgd, '')::NUMERIC,
            NULLIF(r.maxtrfrate, '')::NUMERIC,
            NULLIF(r.totsurchg, '')::NUMERIC,
            COALESCE(NULLIF(r.ratechgd, '')::NUMERIC, 0)
                + COALESCE(NULLIF(r.totsurchg, '')::NUMERIC, 0),
            CASE upper(NULLIF(r.mktbasedrateind, '')) WHEN 'Y' THEN TRUE WHEN 'N' THEN FALSE END,
            CASE upper(NULLIF(r.surchgind, '')) WHEN 'Y' THEN TRUE WHEN 'N' THEN FALSE END,

            NULLIF(r.seasnlst, '')::DATE,
            NULLIF(r.seasnlend, '')::DATE,
            NULLIF(r.kentbegdatetime, '')::TIMESTAMPTZ,
            NULLIF(r.kentenddatetime, '')::TIMESTAMPTZ,
            NULLIF(r.posteddatetime, '')::TIMESTAMPTZ,

            r.source_system,
            r.source_api,
            r.pipeline_run_id,
            f.hash_key,
            r.hash_key
        FROM rate_latest r
        JOIN firm_latest f
              ON f.firmid = r.firmid
        LEFT JOIN loc_latest lr
              ON lr.firmid = r.firmid AND lr.loc = r.recloc
        LEFT JOIN loc_latest ld
              ON ld.firmid = r.firmid AND ld.loc = r.delloc
        ON CONFLICT (firm_id, rate_unique_id) DO UPDATE SET
            contract_id            = EXCLUDED.contract_id,
            tsp_name               = EXCLUDED.tsp_name,
            tsp_duns               = EXCLUDED.tsp_duns,
            contract_holder_name   = EXCLUDED.contract_holder_name,
            rate_schedule          = EXCLUDED.rate_schedule,
            service_request_k      = EXCLUDED.service_request_k,
            contract_qty_dth       = EXCLUDED.contract_qty_dth,
            contract_begin_ts      = EXCLUDED.contract_begin_ts,
            contract_end_ts        = EXCLUDED.contract_end_ts,
            contract_term_days     = EXCLUDED.contract_term_days,
            contract_status_code   = EXCLUDED.contract_status_code,
            contract_status_desc   = EXCLUDED.contract_status_desc,
            is_negotiated_rate     = EXCLUDED.is_negotiated_rate,
            receipt_loc_code       = EXCLUDED.receipt_loc_code,
            receipt_loc_name       = EXCLUDED.receipt_loc_name,
            receipt_zone           = EXCLUDED.receipt_zone,
            receipt_point_qty_dth  = EXCLUDED.receipt_point_qty_dth,
            delivery_loc_code      = EXCLUDED.delivery_loc_code,
            delivery_loc_name      = EXCLUDED.delivery_loc_name,
            delivery_zone          = EXCLUDED.delivery_zone,
            delivery_point_qty_dth = EXCLUDED.delivery_point_qty_dth,
            rate_form_type         = EXCLUDED.rate_form_type,
            rate_form_type_desc    = EXCLUDED.rate_form_type_desc,
            rate_id                = EXCLUDED.rate_id,
            rate_charged           = EXCLUDED.rate_charged,
            max_tariff_rate        = EXCLUDED.max_tariff_rate,
            total_surcharge        = EXCLUDED.total_surcharge,
            all_in_rate            = EXCLUDED.all_in_rate,
            is_market_based_rate   = EXCLUDED.is_market_based_rate,
            has_surcharge          = EXCLUDED.has_surcharge,
            season_start_date      = EXCLUDED.season_start_date,
            season_end_date        = EXCLUDED.season_end_date,
            rate_begin_ts          = EXCLUDED.rate_begin_ts,
            rate_end_ts            = EXCLUDED.rate_end_ts,
            posted_ts              = EXCLUDED.posted_ts,
            source_system          = EXCLUDED.source_system,
            source_api             = EXCLUDED.source_api,
            pipeline_run_id        = EXCLUDED.pipeline_run_id,
            firm_hash_key          = EXCLUDED.firm_hash_key,
            rate_hash_key          = EXCLUDED.rate_hash_key,
            silver_loaded_ts       = now();
        """
