"""Convert, clean, and load a raw 'Workshop Intake' SharePoint/Teams export into
Snowflake, then regenerate Workshops.csv for generate_reports.py.

Export step stays manual: in Teams/SharePoint, open the Workshop Intake list and
use "Export to Excel" (or CSV), save the file, then run this script against it.

Usage (via snow.ps1, which supplies SNOWFLAKE_PAT):
    powershell -ExecutionPolicy Bypass -File snowflake\\snow.ps1 scripts\\load_workshop_intake.py <raw_export.csv>

Flags:
    --dry-run       Parse/clean and print the validation report only; no Snowflake writes.
    --skip-reload   Skip the TRUNCATE+load pipeline and final Workshops.csv regen;
                    only load the raw rows into AXC1195.LANDING_BOOTCAMP_WORKSHOP.
"""
import argparse
import csv
import datetime
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "snowflake"))

RAW_COLUMNS = {
    "oa_name": "OA Name",
    "workshop_date": "Workshop Date",
    "store_number": "Store Number",
    "host_store": "Boot Camp Host Store %23",
    "workshop_type": "Workshop Type",
}

PLACEHOLDER_HOST_STORE = {"N/A", "NA", "TBD", "PENDING", "NONE", "UNKNOWN"}
WORKSHOPS_CSV = BASE_DIR / "Workshops.csv"


def parse_raw_export(path):
    """Returns (cleaned_rows, warnings). cleaned_rows are dicts ready for INSERT."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    missing = [c for c in RAW_COLUMNS.values() if c not in (raw_rows[0].keys() if raw_rows else [])]
    if missing:
        raise ValueError(
            f"Raw export is missing expected column(s): {missing}. "
            f"Found columns: {list(raw_rows[0].keys()) if raw_rows else '(empty file)'}"
        )

    cleaned = []
    warnings = []
    for i, row in enumerate(raw_rows, start=2):  # +2: header is row 1, data starts row 2
        oa_name = row[RAW_COLUMNS["oa_name"]].strip()
        workshop_type = row[RAW_COLUMNS["workshop_type"]].strip()

        date_raw = row[RAW_COLUMNS["workshop_date"]].strip()
        workshop_date = None
        if date_raw:
            for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                try:
                    workshop_date = datetime.datetime.strptime(date_raw, fmt).date().isoformat()
                    break
                except ValueError:
                    continue
        if workshop_date is None:
            warnings.append(f"row {i} ({oa_name!r}): unparseable Workshop Date {date_raw!r} — skipping row")
            continue

        host_raw = row[RAW_COLUMNS["host_store"]].strip()
        host_store = None
        if host_raw:
            if host_raw.upper() in PLACEHOLDER_HOST_STORE:
                pass  # leave as NULL, this is expected/normal
            elif len(host_raw) > 6:
                warnings.append(f"row {i} ({oa_name!r}): Host Store {host_raw!r} is >6 chars — storing as NULL")
            else:
                host_store = host_raw

        store_blob_raw = row[RAW_COLUMNS["store_number"]]
        store_lines = [ln.strip() for ln in store_blob_raw.splitlines() if ln.strip()]
        bad_lines = [ln for ln in store_lines if not re.match(r"^[0-9]{1,6}$", ln)]
        if bad_lines:
            warnings.append(f"row {i} ({oa_name!r}): non-numeric store number line(s) {bad_lines} — will be filtered at load")
        if not store_lines:
            warnings.append(f"row {i} ({oa_name!r}): no store numbers at all — skipping row")
            continue
        store_blob = "\n".join(store_lines)

        if not oa_name:
            warnings.append(f"row {i}: blank OA Name — skipping row")
            continue
        if workshop_type.upper() not in ("BOOT CAMP", "RISING STAR"):
            warnings.append(f"row {i} ({oa_name!r}): unrecognized Workshop Type {workshop_type!r} — loading as-is")

        cleaned.append({
            "OA_NAME": oa_name,
            "WORKSHOP_DATE": workshop_date,
            "WORKSHOP_TYPE": workshop_type,
            "HOST_STORE": host_store,
            "STORE_NUMBER": store_blob,
        })

    return cleaned, warnings


def _sql_literal(value):
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


LOAD_PIPELINE_SQL = [
    "TRUNCATE TABLE AXC1195.WORKSHOP",
    "TRUNCATE TABLE AXC1195.WORKSHOP_RESTAURANT",
    """
    CREATE OR REPLACE TRANSIENT TABLE AXC1195.TMP_LANDING_BOOTCAMP_WORKSHOP AS
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY OA_NAME, WORKSHOP_DATE, WORKSHOP_TYPE, HOST_STORE, STORE_NUMBER
        ) AS LANDING_ID,
        *
    FROM AXC1195.LANDING_BOOTCAMP_WORKSHOP
    """,
    """
    INSERT INTO AXC1195.WORKSHOP (LANDING_ID, OA_NAME, WORKSHOP_DATE, WORKSHOP_TYPE, HOST_STORE)
    SELECT LANDING_ID, OA_NAME, WORKSHOP_DATE, WORKSHOP_TYPE, HOST_STORE
    FROM AXC1195.TMP_LANDING_BOOTCAMP_WORKSHOP
    """,
    """
    INSERT INTO AXC1195.WORKSHOP_RESTAURANT (WORKSHOP_ID, STORE_NUMBER, TRAINING_ASSIGNED, TRAINING_COMPLETED)
    WITH WORKSHOP_STORES AS (
        SELECT DISTINCT
            W.WORKSHOP_ID,
            W.WORKSHOP_TYPE,
            LPAD(TRIM(F.VALUE::STRING), 6, '0') AS STORE_NUMBER
        FROM AXC1195.TMP_LANDING_BOOTCAMP_WORKSHOP L
        JOIN AXC1195.WORKSHOP W ON W.LANDING_ID = L.LANDING_ID
        ,LATERAL FLATTEN(INPUT => SPLIT(REPLACE(L.STORE_NUMBER, CHAR(13), ''),CHAR(10))) F
        WHERE TRIM(F.VALUE::STRING) <> ''
          AND REGEXP_LIKE(LPAD(TRIM(F.VALUE::STRING), 6, '0'),'^[0-9]{6}$')
    ),
    DIRECT_TRAINING AS (
        SELECT DISTINCT
            WS.WORKSHOP_ID,
            WS.STORE_NUMBER,
            P.USER_NETWORK_ID,
            CASE WHEN F.PATH_STATUS_ID = 100 THEN 1 ELSE 0 END AS COMPLETED_IND
        FROM WORKSHOP_STORES WS
        JOIN DSC.LP_PERSON_DIM_V1 P ON TRIM(P.STORE_ID) = TRIM(WS.STORE_NUMBER)
        JOIN DSC.LP_LRN_ACTIV_FACT_V1 F ON F.DW_LP_PERSON = P.DW_LP_PERSON
        WHERE P.EMPL_STATUS = 'Active' AND REGEXP_LIKE(TRIM(P.STORE_ID),'^[0-9]{6}$')
          AND F.CERT_ID = CASE
              WHEN UPPER(WS.WORKSHOP_TYPE) LIKE '%BOOT%' THEN 'phus-OGPIB-product-quality-boot-camp-2026'
              WHEN UPPER(WS.WORKSHOP_TYPE) LIKE '%RISING%' THEN 'phus-rgm-rally-2026'
              ELSE NULL
          END
    ),
    TRAINING_BY_STORE AS (
        SELECT
            WORKSHOP_ID,
            STORE_NUMBER,
            COUNT(DISTINCT USER_NETWORK_ID) AS TRAINING_ASSIGNED,
            COUNT(DISTINCT CASE WHEN COMPLETED_IND = 1 THEN USER_NETWORK_ID END) AS TRAINING_COMPLETED
        FROM DIRECT_TRAINING
        GROUP BY WORKSHOP_ID, STORE_NUMBER
    )
    SELECT
        WS.WORKSHOP_ID,
        WS.STORE_NUMBER,
        COALESCE(T.TRAINING_ASSIGNED,0) AS TRAINING_ASSIGNED,
        COALESCE(T.TRAINING_COMPLETED,0) AS TRAINING_COMPLETED
    FROM WORKSHOP_STORES WS
    LEFT JOIN TRAINING_BY_STORE T ON WS.WORKSHOP_ID = T.WORKSHOP_ID AND WS.STORE_NUMBER = T.STORE_NUMBER
    """,
    """
    UPDATE AXC1195.WORKSHOP W
    SET
        ARL_TRAINING_ASSIGNED = X.ARL_TRAINING_ASSIGNED,
        ARL_TRAINING_COMPLETED = X.ARL_TRAINING_COMPLETED
    FROM (
        WITH RECURSIVE
        WORKSHOP_STORES AS (
            SELECT DISTINCT
                W2.WORKSHOP_ID,
                W2.WORKSHOP_TYPE,
                WR.STORE_NUMBER
            FROM AXC1195.WORKSHOP W2
            JOIN AXC1195.WORKSHOP_RESTAURANT WR ON W2.WORKSHOP_ID = WR.WORKSHOP_ID
        ),
        PEOPLE AS (
            SELECT DISTINCT
                PERSON_ID, DW_LP_PERSON, USER_NETWORK_ID, ROLE_NM, STORE_ID, MGR_ID
            FROM DSC.LP_PERSON_DIM_V1
            WHERE EMPL_STATUS = 'Active'
        ),
        STORE_PEOPLE AS (
            SELECT DISTINCT
                WS.WORKSHOP_ID, WS.WORKSHOP_TYPE, WS.STORE_NUMBER, P.PERSON_ID, P.MGR_ID
            FROM WORKSHOP_STORES WS
            JOIN PEOPLE P ON TRIM(P.STORE_ID) = TRIM(WS.STORE_NUMBER)
            WHERE REGEXP_LIKE(TRIM(P.STORE_ID),'^[0-9]{6}$')
        ),
        MANAGEMENT_CHAIN AS (
            SELECT
                SP.WORKSHOP_ID, SP.WORKSHOP_TYPE, SP.STORE_NUMBER,
                SP.PERSON_ID AS CURRENT_PERSON_ID, SP.MGR_ID AS NEXT_MGR_ID, 0 AS HIERARCHY_LEVEL
            FROM STORE_PEOPLE SP
            UNION ALL
            SELECT
                MC.WORKSHOP_ID, MC.WORKSHOP_TYPE, MC.STORE_NUMBER,
                M.PERSON_ID AS CURRENT_PERSON_ID, M.MGR_ID AS NEXT_MGR_ID, MC.HIERARCHY_LEVEL + 1
            FROM MANAGEMENT_CHAIN MC
            JOIN PEOPLE M ON MC.NEXT_MGR_ID = M.PERSON_ID
            WHERE MC.HIERARCHY_LEVEL < 10
        ),
        ASSOCIATED_PEOPLE AS (
            SELECT DISTINCT
                MC.WORKSHOP_ID, P.PERSON_ID, P.DW_LP_PERSON, P.USER_NETWORK_ID, P.STORE_ID
            FROM MANAGEMENT_CHAIN MC
            JOIN PEOPLE P ON MC.CURRENT_PERSON_ID = P.PERSON_ID
        ),
        ARL_TRAINING AS (
            SELECT DISTINCT
                AP.WORKSHOP_ID, AP.PERSON_ID, AP.USER_NETWORK_ID, F.PATH_STATUS_ID
            FROM ASSOCIATED_PEOPLE AP
            JOIN AXC1195.WORKSHOP W2 ON AP.WORKSHOP_ID = W2.WORKSHOP_ID
            JOIN DSC.LP_LRN_ACTIV_FACT_V1 F ON AP.DW_LP_PERSON = F.DW_LP_PERSON
            WHERE NOT REGEXP_LIKE(TRIM(AP.STORE_ID),'^[0-9]{6}$')
            AND F.CERT_ID = CASE
                WHEN UPPER(W2.WORKSHOP_TYPE) LIKE '%BOOT%' THEN 'phus-OGPIB-product-quality-boot-camp-2026'
                WHEN UPPER(W2.WORKSHOP_TYPE) LIKE '%RISING%' THEN 'phus-rgm-rally-2026'
                ELSE NULL
            END
        ),
        UNIQUE_ARLS AS (
            SELECT
                WORKSHOP_ID, USER_NETWORK_ID,
                MAX(CASE WHEN PATH_STATUS_ID = 100 THEN 1 ELSE 0 END) AS COMPLETED_IND
            FROM ARL_TRAINING
            GROUP BY WORKSHOP_ID, USER_NETWORK_ID
        )
        SELECT
            WORKSHOP_ID,
            COUNT(DISTINCT USER_NETWORK_ID) AS ARL_TRAINING_ASSIGNED,
            COUNT(DISTINCT CASE WHEN COMPLETED_IND = 1 THEN USER_NETWORK_ID END) AS ARL_TRAINING_COMPLETED
        FROM UNIQUE_ARLS
        GROUP BY WORKSHOP_ID
    ) X
    WHERE W.WORKSHOP_ID = X.WORKSHOP_ID
    """,
]

FINAL_SELECT_SQL = """
    SELECT
        WR.STORE_NUMBER,
        W.WORKSHOP_ID,
        W.WORKSHOP_DATE,
        W.WORKSHOP_TYPE,
        W.HOST_STORE,
        W.OA_NAME
    FROM AXC1195.WORKSHOP W
    INNER JOIN AXC1195.WORKSHOP_RESTAURANT WR ON W.WORKSHOP_ID = WR.WORKSHOP_ID
    ORDER BY W.WORKSHOP_DATE, WR.STORE_NUMBER
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw_export", help="Path to the raw Workshop Intake export (.csv)")
    ap.add_argument("--dry-run", action="store_true", help="Parse/clean only, print report, no Snowflake writes")
    ap.add_argument("--skip-reload", action="store_true", help="Load landing rows only, skip TRUNCATE+load pipeline and Workshops.csv regen")
    args = ap.parse_args()

    cleaned, warnings = parse_raw_export(args.raw_export)

    print(f"Parsed {len(cleaned)} workshop row(s) from {args.raw_export}")
    if warnings:
        print(f"\n{len(warnings)} validation warning(s):")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("No validation warnings.")

    if args.dry_run:
        print("\n--dry-run: stopping before any Snowflake writes.")
        return

    from snow_client import query, epoch_to_date

    print("\nTruncating AXC1195.LANDING_BOOTCAMP_WORKSHOP ...")
    query("TRUNCATE TABLE AXC1195.LANDING_BOOTCAMP_WORKSHOP")

    print(f"Inserting {len(cleaned)} row(s) into AXC1195.LANDING_BOOTCAMP_WORKSHOP ...")
    BATCH_SIZE = 100
    for i in range(0, len(cleaned), BATCH_SIZE):
        batch = cleaned[i:i + BATCH_SIZE]
        values_sql = ",\n".join(
            "(" + ", ".join([
                _sql_literal(r["OA_NAME"]),
                _sql_literal(r["WORKSHOP_DATE"]),
                _sql_literal(r["STORE_NUMBER"]),
                _sql_literal(r["HOST_STORE"]),
                _sql_literal(r["WORKSHOP_TYPE"]),
            ]) + ")"
            for r in batch
        )
        insert_sql = (
            "INSERT INTO AXC1195.LANDING_BOOTCAMP_WORKSHOP "
            "(OA_NAME, WORKSHOP_DATE, STORE_NUMBER, HOST_STORE, WORKSHOP_TYPE) VALUES\n"
            + values_sql
        )
        query(insert_sql)

    if args.skip_reload:
        print("\n--skip-reload: landing table loaded, stopping before WORKSHOP/WORKSHOP_RESTAURANT pipeline.")
        return

    print("\nRunning WORKSHOP / WORKSHOP_RESTAURANT load pipeline ...")
    for i, stmt in enumerate(LOAD_PIPELINE_SQL, start=1):
        print(f"  step {i}/{len(LOAD_PIPELINE_SQL)} ...")
        query(stmt)

    print("Querying final workshop list and writing Workshops.csv ...")
    columns, rows = query(FINAL_SELECT_SQL)
    date_col = columns.index("WORKSHOP_DATE")
    rows = [
        [epoch_to_date(v).isoformat() if i == date_col and v is not None else v
         for i, v in enumerate(row)]
        for row in rows
    ]
    with open(WORKSHOPS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)

    print(f"\nDone. {len(rows)} workshop-store row(s) written to {WORKSHOPS_CSV}")


if __name__ == "__main__":
    main()
