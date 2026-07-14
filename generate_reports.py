import pandas as pd
import numpy as np
import json
import re
import os
import hashlib
import urllib.request
import base64
from pathlib import Path
from scipy.stats import pearsonr

# Optional Snowflake connector
try:
    import snowflake.connector
    HAS_SNOWFLAKE = True
except ImportError:
    HAS_SNOWFLAKE = False

# ─── Config ────────────────────────────────────────────────────────────────
BASE_DIR = Path("C:/Users/axc1195/OneDrive - Yum! Brands, Inc/Documents/5-Star/Reporting")
FIVESTAR_CSV = BASE_DIR / "5-Star.csv"
STORE_LIST_CSV = BASE_DIR / "Store List - 7-7-26 v2.csv"
WORKSHOPS_CSV = BASE_DIR / "Workshops.csv"
OUTPUT_DIR = BASE_DIR

TIER_THRESHOLD = 2.5  # T1 < 2.5, T2 >= 2.5 & < 4.0, T3 >= 4.0
DEFAULT_THRESHOLD = 2.0  # < 2.0 is a "Failure to Satisfy" per brand standards
PERIODS = []  # set dynamically from data
MONTH_LABELS = []  # set dynamically from data
PERIOD_MONTHS = []  # month numbers [1..N] detected from data

STAR_COLS = ["WIN_SCORE_STAR", "SPEED_STAR", "BRAND_STAR", "HB_ONTIME_STAR", "FSCC_STAR"]
STAR_LABELS = {
    "WIN_SCORE_STAR": "Win Score", "SPEED_STAR": "Speed",
    "BRAND_STAR": "Brand", "HB_ONTIME_STAR": "Hutbot", "FSCC_STAR": "FSCC"
}
STAR_COLORS = {
    "WIN_SCORE_STAR": "#a3122a", "SPEED_STAR": "#c07f1f",
    "HB_ONTIME_STAR": "#5b7a9e", "BRAND_STAR": "#7a5ba3", "FSCC_STAR": "#6b6560"
}
BINDING_ORDER = ["WIN_SCORE_STAR", "SPEED_STAR", "BRAND_STAR", "HB_ONTIME_STAR", "FSCC_STAR"]

TIER_COLORS = {1: "#a3122a", 2: "#c07f1f", 3: "#276b4d"}
TIER_NAMES = {1: "Bootcamp", 2: "Rising Star", 3: "Top Tier"}

# OpenCode server config (used for LLM summaries)
_OC_URL = os.environ.get("OPENCODE_SERVER_URL", "")
OPENCODE_SERVER_USER = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
OPENCODE_SERVER_PASS = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
SUMMARIES_CACHE = BASE_DIR / "_summaries.json"


def _detect_opencode_url():
    """Auto-detect the opencode server URL from running processes."""
    if _OC_URL:
        return _OC_URL
    try:
        import subprocess, sys
        out = subprocess.check_output(
            ["netstat", "-ano"], shell=True, text=True, timeout=5
        )
        # Parse lines like: TCP 127.0.0.1:64771 0.0.0.0:0 LISTENING 10460
        opencode_pids = set()
        # Get opencode process PIDs
        task_out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq OpenCode.exe", "/FO", "CSV"],
            shell=True, text=True, timeout=5
        )
        for line in task_out.strip().split("\n"):
            if "OpenCode.exe" in line:
                parts = line.split(",")
                if len(parts) >= 2:
                    pid = parts[1].strip().strip('"')
                    opencode_pids.add(pid)
        # Find matching listening port
        for line in out.strip().split("\n"):
            if "LISTENING" in line and "127.0.0.1" in line:
                cols = line.split()
                if len(cols) >= 5:
                    addr = cols[1]
                    pid = cols[4]
                    if pid in opencode_pids and ":" in addr:
                        port = addr.rsplit(":", 1)[-1]
                        return f"http://127.0.0.1:{port}"
    except Exception:
        pass
    return "http://127.0.0.1:62464"


OPENCODE_SERVER_URL = _detect_opencode_url()
# Extend timeout for LLM calls (15 OA summaries is a lot of tokens)
_LLM_TIMEOUT = 300  # seconds

# Snowflake config (optional — set env vars to enable)
SNOWFLAKE_ACCOUNT = os.environ.get("SNOWFLAKE_ACCOUNT", "")
SNOWFLAKE_USER = os.environ.get("SNOWFLAKE_USER", "")
SNOWFLAKE_PASSWORD = os.environ.get("SNOWFLAKE_PASSWORD", "")
SNOWFLAKE_WAREHOUSE = os.environ.get("SNOWFLAKE_WAREHOUSE", "")
SNOWFLAKE_DATABASE = os.environ.get("SNOWFLAKE_DATABASE", "")
SNOWFLAKE_SCHEMA = os.environ.get("SNOWFLAKE_SCHEMA", "")
SNOWFLAKE_ENABLED = all([SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD])


# ─── Helpers ───────────────────────────────────────────────────────────────

def classify_tier(score):
    if pd.isna(score):
        return None
    if score < TIER_THRESHOLD:
        return 1
    if score < 4.0:
        return 2
    return 3


def get_binding(row):
    """Determine which 5-Star component is the binding constraint.
    Uses minimum STAR value; ties broken by priority order:
    Win > Speed > Brand > HB > FSCC (order in BINDING_ORDER).
    """
    best_val = 99
    best_key = None
    for k in BINDING_ORDER:
        v = row.get(k)
        if pd.isna(v):
            continue
        v = float(v)
        if v < best_val:
            best_val = v
            best_key = k
    return best_key


def safe_json(val):
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val


def get_binding_for_store(sid, zone_df):
    """Get the binding component for a store from its latest month in zone_df."""
    sub = zone_df[zone_df["CHAINED_STORE_ID"].astype(str).str.zfill(5).str[-5:] == sid]
    if len(sub) == 0:
        sub = zone_df[zone_df["CHAINED_STORE_ID"].astype(str).str.contains(sid)]
    if len(sub) > 0:
        latest = sub.loc[sub["MONTHNUM"].idxmax()]
        return get_binding(latest.to_dict()) if pd.notna(latest.get("OVERALL_FIVESTAR")) else None
    return None


def convert_for_json(obj):
    """Recursively convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_for_json(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_for_json(v) for v in obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    return obj


# ─── Data Loading ──────────────────────────────────────────────────────────

def load_data():
    print("Loading 5-Star.csv...")
    df = pd.read_csv(
        FIVESTAR_CSV,
        low_memory=False,
        dtype={"CHAINED_STORE_ID": str},
    )
    # Parse numeric columns
    for c in ["MONTHNUM"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in ["OVERALL_FIVESTAR"] + STAR_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    print(f"  {len(df):,} rows loaded")

    # Try loading store list (optional — provides Area, Lat/Long, FOP)
    store_list_loaded = False
    if STORE_LIST_CSV.exists():
        print("Loading store list...")
        try:
            stores = pd.read_csv(
                STORE_LIST_CSV,
                dtype={"CHAINED_STORE_ID": str},
            )
            print(f"  {len(stores):,} stores loaded")

            # Join: bring Area, Lat/Long, DMA, Franchisee, FOP from store list
            join_cols = ["CHAINED_STORE_ID"]
            store_cols = ["CHAINED_STORE_ID", "FREGIONDESC", "FAREADESC",
                          "LATITUDE", "LONGITUDE", "CURR_FRAN_OWNER_NM",
                          "NIELSENDMADESC"]
            # Add FOP if available in store list
            if "FOP" in stores.columns:
                store_cols.append("FOP")
                join_cols.append("FOP")

            df = df.merge(
                stores[store_cols],
                on=join_cols if len(join_cols) > 1 else "CHAINED_STORE_ID",
                how="left",
                suffixes=("", "_sl")
            )

            # Fill missing fran/dma from the 5-Star CSV if store list missing
            if "CURR_FRAN_OWNER_NM_sl" in df.columns:
                sfm = df["CURR_FRAN_OWNER_NM_sl"].notna()
                df.loc[sfm, "CURR_FRAN_OWNER_NM"] = df.loc[sfm, "CURR_FRAN_OWNER_NM_sl"]
            if "NIELSENDMADESC_sl" in df.columns:
                sdm = df["NIELSENDMADESC_sl"].notna()
                df.loc[sdm, "NIELSENDMADESC"] = df.loc[sdm, "NIELSENDMADESC_sl"]
            if "FOP_sl" in df.columns:
                sfp = df["FOP_sl"].notna()
                df.loc[sfp, "FOP"] = df.loc[sfp, "FOP_sl"]

            store_list_loaded = True
            print(f"  Joined: {len(df):,} rows")
        except Exception as e:
            print(f"  Store list load failed: {e}, proceeding without it")

    if not store_list_loaded:
        print("  No store list — using 5-Star CSV fields only")
        # Ensure lat/long columns exist as placeholders
        for c in ["LATITUDE", "LONGITUDE", "FAREADESC", "FREGIONDESC"]:
            if c not in df.columns:
                df[c] = None

    # Ensure FOP column exists (check OPX_FOP first, then FOP)
    if "OPX_FOP" in df.columns:
        df = df.rename(columns={"OPX_FOP": "FOP"})
    if "FOP" not in df.columns:
        df["FOP"] = "Unknown"

    # Ensure Director column exists (check OPX_DIRECTOR, then DIRECTOR)
    if "OPX_DIRECTOR" in df.columns:
        df = df.rename(columns={"OPX_DIRECTOR": "DIRECTOR"})
    if "DIRECTOR" not in df.columns:
        df["DIRECTOR"] = "Unknown"

    return df


# OA name normalization (fixes typos in source CSVs)
_OA_NAME_FIXES = {"Hellen Lobacarro": "Hellen Lobaccaro"}


def load_workshops(df):
    """Load Workshops.csv, parse dates, compute benchmark month, and join to main df for scores.
    Returns a dict of workshop data grouped by OA_NAME."""
    if not WORKSHOPS_CSV.exists():
        print("  Workshops.csv not found, skipping workshop data")
        return {}

    w = pd.read_csv(WORKSHOPS_CSV, dtype={"STORE_NUMBER": str})
    if w.empty:
        return {}

    w["STORE_NUMBER"] = w["STORE_NUMBER"].str.strip()
    w["OA_NAME"] = w["OA_NAME"].str.strip().replace(_OA_NAME_FIXES)
    w["WORKSHOP_DATE"] = pd.to_datetime(w["WORKSHOP_DATE"], errors="coerce")
    w["workshop_month"] = w["WORKSHOP_DATE"].dt.month.astype(int)
    w["workshop_day"] = w["WORKSHOP_DATE"].dt.day.astype(int)

    last_data_month = PERIOD_MONTHS[-1] if PERIOD_MONTHS else 6

    results = {}
    for _, row in w.iterrows():
        sid = row["STORE_NUMBER"]
        oa = row["OA_NAME"]
        ws_month = int(row["workshop_month"])
        ws_day = int(row["workshop_day"]) if pd.notna(row.get("workshop_day")) else 1
        bm_month = ws_month if ws_day > 14 else ws_month - 1
        ws_type = str(row["WORKSHOP_TYPE"]).strip()
        date_str = str(row["WORKSHOP_DATE"].strftime("%Y-%m-%d")) if pd.notna(row["WORKSHOP_DATE"]) else ""

        # Classify: future if workshop month > last data month
        if ws_month > last_data_month:
            status = "future"
        elif ws_month == last_data_month:
            status = "current"
        else:
            status = "past"

        # Get benchmark score from main df (month before workshop)
        bench_score = None
        bench_tier = None
        bench_binding = None
        if bm_month >= 1 and bm_month <= 12:
            bm_row = df[(df["CHAINED_STORE_ID"] == sid) & (df["MONTHNUM"] == bm_month)]
            if not bm_row.empty:
                r = bm_row.iloc[0]
                bench_score = round(float(r["OVERALL_FIVESTAR"]), 2) if pd.notna(r["OVERALL_FIVESTAR"]) else None
                bench_tier = int(r["_tier"]) if pd.notna(r["_tier"]) else None
                bench_binding = str(r["_binding"]) if pd.notna(r["_binding"]) else None

        # Get post-workshop scores (months after workshop, up to last data month)
        post_scores = []
        for pm in range(ws_month + 1, last_data_month + 1):
            pm_row = df[(df["CHAINED_STORE_ID"] == sid) & (df["MONTHNUM"] == pm)]
            if not pm_row.empty:
                ps = round(float(pm_row.iloc[0]["OVERALL_FIVESTAR"]), 2) if pd.notna(pm_row.iloc[0]["OVERALL_FIVESTAR"]) else None
                if ps is not None:
                    post_scores.append({
                        "month": int(pm),
                        "label": MONTH_LABELS[PERIOD_MONTHS.index(pm)] if pm in PERIOD_MONTHS else str(pm),
                        "score": ps,
                    })

        entry = {
            "store": sid,
            "date": date_str,
            "type": ws_type,
            "workshop_month": ws_month,
            "benchmark_month": bm_month,
            "benchmark_score": bench_score,
            "benchmark_tier": bench_tier,
            "benchmark_binding": bench_binding,
            "post_scores": post_scores,
            "status": status,
        }

        if "rising" in ws_type.lower():
            type_key = "rising_star"
        else:
            type_key = "boot_camp"
        results.setdefault(oa, {}).setdefault(type_key, []).append(entry)

    # Add summary counts per OA for both types
    for oa in results:
        for tk in ("boot_camp", "rising_star"):
            lst = results[oa].get(tk, [])
            results[oa][f"n_{tk}_past"] = sum(1 for e in lst if e["status"] == "past")
            results[oa][f"n_{tk}_future"] = sum(1 for e in lst if e["status"] == "future")

    total_bc = sum(len(v.get("boot_camp", [])) for v in results.values())
    total_rs = sum(len(v.get("rising_star", [])) for v in results.values())
    print(f"  Loaded {len(w)} workshops ({total_bc} boot camp, {total_rs} rising star), {len(results)} OAs represented")
    return results


def compute_workshop_effectiveness(df, workshops_by_oa):
    """Compute control vs variable effectiveness for workshops nationally."""
    last_m = PERIOD_MONTHS[-1] if PERIOD_MONTHS else 6
    last_label = MONTH_LABELS[-1] if MONTH_LABELS else str(last_m)

    def _effectiveness(entries, ws_type_label):
        """Compare stores with workshops vs all other stores."""
        ws_stores = set()
        ws_improvements = []
        benchmark_month_set = set()

        for e in entries:
            if e["status"] != "past":
                continue
            sid = e["store"]
            ws_stores.add(sid)
            bm = e["benchmark_month"]
            benchmark_month_set.add(bm)
            if e["benchmark_score"] is not None and e["post_scores"]:
                latest_post = max(e["post_scores"], key=lambda x: x["month"])
                imp = latest_post["score"] - e["benchmark_score"]
                ws_improvements.append(imp)

        if not benchmark_month_set:
            return None

        avg_bm = int(min(benchmark_month_set)) if benchmark_month_set else last_m - 1
        # Control: stores in same benchmark month range that didn't get workshops
        control_improvements = []
        for sid in df["CHAINED_STORE_ID"].unique():
            if sid in ws_stores:
                continue
            bm_row = df[(df["CHAINED_STORE_ID"] == sid) & (df["MONTHNUM"] == avg_bm)]
            latest_row = df[(df["CHAINED_STORE_ID"] == sid) & (df["MONTHNUM"] == last_m)]
            if not bm_row.empty and not latest_row.empty:
                bs = bm_row.iloc[0]["OVERALL_FIVESTAR"]
                ls = latest_row.iloc[0]["OVERALL_FIVESTAR"]
                if pd.notna(bs) and pd.notna(ls):
                    control_improvements.append(float(ls) - float(bs))

        var_n = len(ws_improvements)
        ctrl_n = len(control_improvements)

        var_avg_bm = None
        var_avg_lt = None
        ctrl_avg_bm = None
        ctrl_avg_lt = None

        if entries:
            bm_scores = [e["benchmark_score"] for e in entries if e["benchmark_score"] is not None and e["status"] == "past"]
            lt_scores = []
            for e in entries:
                if e["status"] != "past" or not e["post_scores"]:
                    continue
                lt = max(e["post_scores"], key=lambda x: x["month"])
                lt_scores.append(lt["score"])
            if bm_scores:
                var_avg_bm = round(sum(bm_scores) / len(bm_scores), 2)
            if lt_scores:
                var_avg_lt = round(sum(lt_scores) / len(lt_scores), 2)

        if control_improvements:
            ctrl_bm_scores = []
            ctrl_lt_scores = []
            for sid in df["CHAINED_STORE_ID"].unique():
                if sid in ws_stores:
                    continue
                bm_row = df[(df["CHAINED_STORE_ID"] == sid) & (df["MONTHNUM"] == avg_bm)]
                latest_row = df[(df["CHAINED_STORE_ID"] == sid) & (df["MONTHNUM"] == last_m)]
                if not bm_row.empty and not latest_row.empty:
                    bs = bm_row.iloc[0]["OVERALL_FIVESTAR"]
                    ls = latest_row.iloc[0]["OVERALL_FIVESTAR"]
                    if pd.notna(bs) and pd.notna(ls):
                        ctrl_bm_scores.append(float(bs))
                        ctrl_lt_scores.append(float(ls))
            if ctrl_bm_scores:
                ctrl_avg_bm = round(sum(ctrl_bm_scores) / len(ctrl_bm_scores), 2)
            if ctrl_lt_scores:
                ctrl_avg_lt = round(sum(ctrl_lt_scores) / len(ctrl_lt_scores), 2)

        var_imp = round(sum(ws_improvements) / len(ws_improvements), 3) if ws_improvements else None
        ctrl_imp = round(sum(control_improvements) / len(control_improvements), 3) if control_improvements else None

        return {
            "n_workshops": len(entries),
            "n_stores": len(ws_stores),
            "n_future": sum(1 for e in entries if e["status"] == "future"),
            "benchmark_period": f"M{avg_bm}",
            "latest_period": last_label,
            "variable": {
                "n": var_n,
                "avg_benchmark": var_avg_bm,
                "avg_latest": var_avg_lt,
                "avg_improvement": var_imp,
            },
            "control": {
                "n": ctrl_n,
                "avg_benchmark": ctrl_avg_bm,
                "avg_latest": ctrl_avg_lt,
                "avg_improvement": ctrl_imp,
            },
        }

    all_boot = []
    all_rising = []
    for oa, odata in workshops_by_oa.items():
        all_boot.extend(odata.get("boot_camp", []))
        all_rising.extend(odata.get("rising_star", []))

    result = {}
    bc = _effectiveness(all_boot, "Boot Camp")
    if bc:
        result["boot_camp"] = bc
    rs = _effectiveness(all_rising, "Rising Star")
    if rs:
        result["rising_star"] = rs

    return result


def filter_analysis_data(df):
    """Filter to active stores Jan-Dec 2026 with valid 5-Star scores.
    Detects available months and sets global PERIODS, MONTH_LABELS, PERIOD_MONTHS."""
    global PERIODS, MONTH_LABELS, PERIOD_MONTHS

    df = df.copy()
    df["_year"] = df["YEARNO"].astype(str).str.extract(r"(\d{4})").astype(float)

    mask = (
        (df["STATUSDESC"] == "Open")
        & (df["_year"] == 2026)
        & (df["OVERALL_FIVESTAR"].notna())
    )
    filtered = df[mask].copy()

    # Detect available months from actual data
    available = sorted(filtered["MONTHNUM"].dropna().unique().astype(int))
    # Filter to only those months
    filtered = filtered[filtered["MONTHNUM"].isin(available)]

    PERIOD_MONTHS.clear()
    PERIODS.clear()
    MONTH_LABELS.clear()
    MONTH_NAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    for m in available:
        PERIOD_MONTHS.append(m)
        period = 202600 + m
        PERIODS.append(period)
        MONTH_LABELS.append(MONTH_NAMES.get(m, f"M{m}"))

    first = MONTH_NAMES.get(available[0], f"M{available[0]}")
    last = MONTH_NAMES.get(available[-1], f"M{available[-1]}")
    print(f"  Filtered to {first}-{last} 2026 active with scores: {len(filtered):,} rows")
    print(f"  Months detected: {available}")
    return filtered


# ─── Tier Flows ────────────────────────────────────────────────────────────

def compute_tier_flows(monthly_by_store):
    """From store-month data, compute tier transitions from first to last month."""
    first_m = PERIOD_MONTHS[0] if PERIOD_MONTHS else 1
    last_m = PERIOD_MONTHS[-1] if PERIOD_MONTHS else 5
    first_df = monthly_by_store[monthly_by_store["MONTHNUM"] == first_m].copy()
    last_df = monthly_by_store[monthly_by_store["MONTHNUM"] == last_m].copy()

    first_df.rename(columns={"OVERALL_FIVESTAR": "score_first", "_tier": "tier_first"}, inplace=True)
    last_df.rename(columns={"OVERALL_FIVESTAR": "score_last", "_tier": "tier_last"}, inplace=True)

    merged = first_df[["CHAINED_STORE_ID", "score_first", "tier_first"]].merge(
        last_df[["CHAINED_STORE_ID", "score_last", "tier_last"]],
        on="CHAINED_STORE_ID",
        how="inner"
    )

    start_counts = {1: 0, 2: 0, 3: 0}
    end_counts = {1: 0, 2: 0, 3: 0}
    flows = {f"{f}_{t}": 0 for f in [1, 2, 3] for t in [1, 2, 3]}
    moved_up = 0
    moved_down = 0

    for _, r in merged.iterrows():
        sj, sm = int(r["tier_first"]), int(r["tier_last"])
        start_counts[sj] = start_counts.get(sj, 0) + 1
        end_counts[sm] = end_counts.get(sm, 0) + 1
        flows[f"{sj}_{sm}"] = flows.get(f"{sj}_{sm}", 0) + 1
        if sm > sj:
            moved_up += 1
        elif sm < sj:
            moved_down += 1

    tier_story = []
    for t in [1, 2, 3]:
        sub = merged[merged["tier_first"] == t]
        if len(sub) == 0:
            tier_story.append({"t": t, "n": 0, "avgStart": 0, "avgEnd": 0,
                               "stayed": 0, "up": 0, "down": 0})
            continue
        stayed = int((sub["tier_last"] == t).sum())
        up = int((sub["tier_last"] > t).sum()) if t < 3 else 0
        down = int((sub["tier_last"] < t).sum()) if t > 1 else 0
        tier_story.append({
            "t": t,
            "n": len(sub),
            "avgStart": round(float(sub["score_first"].mean()), 2),
            "avgEnd": round(float(sub["score_last"].mean()), 2),
            "stayed": stayed,
            "up": up,
            "down": down,
        })

    flows_list = []
    for f in [1, 2, 3]:
        for t in [1, 2, 3]:
            v = flows.get(f"{f}_{t}", 0)
            if v > 0:
                flows_list.append({"from": f, "to": t, "v": v})

    return {
        "startCounts": start_counts,
        "endCounts": end_counts,
        "flows": flows_list,
        "moved_up": moved_up,
        "moved_down": moved_down,
        "tier_story": tier_story,
        "merged": merged,
    }


# ─── Leadership Summary ────────────────────────────────────────────────────

def compute_leadership(df):
    """Compute national-level leadership summary data."""
    print("Computing leadership summary...")

    # Monthly national averages
    monthly = []
    for p in PERIODS:
        m = p % 100
        sub = df[df["MONTHNUM"] == m]
        if len(sub) == 0:
            continue
        t1c = int((sub["_tier"] == 1).sum())
        t2c = int((sub["_tier"] == 2).sum())
        t3c = int((sub["_tier"] == 3).sum())
        monthly.append({
            "period": p,
            "avg": round(float(sub["OVERALL_FIVESTAR"].mean()), 3),
            "n": len(sub),
            "t1": t1c,
            "t2": t2c,
            "t3": t3c,
            "win": round(float(sub["WIN_SCORE_STAR"].mean()), 3) if sub["WIN_SCORE_STAR"].notna().any() else 0,
            "speed": round(float(sub["SPEED_STAR"].mean()), 3) if sub["SPEED_STAR"].notna().any() else 0,
            "fscc": round(float(sub["FSCC_STAR"].mean()), 3) if sub["FSCC_STAR"].notna().any() else 0,
            "brand": round(float(sub["BRAND_STAR"].mean()), 3) if sub["BRAND_STAR"].notna().any() else 0,
            "hb": round(float(sub["HB_ONTIME_STAR"].mean()), 3) if sub["HB_ONTIME_STAR"].notna().any() else 0,
        })

    latest_n = monthly[-1]["n"] if monthly else 0

    # Tier flows (national)
    flows = compute_tier_flows(df)

    last_m = PERIOD_MONTHS[-1] if PERIOD_MONTHS else 5
    first_m = PERIOD_MONTHS[0] if PERIOD_MONTHS else 1
    may_df = df[df["MONTHNUM"] == last_m]
    jan_df = df[df["MONTHNUM"] == first_m]

    # Zone rankings
    oa_list = []
    for oa in sorted(df["OPX_OA"].dropna().unique()):
        m_sub = may_df[may_df["OPX_OA"] == oa]
        j_sub = jan_df[jan_df["OPX_OA"] == oa]
        if len(m_sub) == 0:
            continue

        t1_latest = int((m_sub["_tier"] == 1).sum())
        t1_base = int((j_sub["_tier"] == 1).sum()) if len(j_sub) > 0 else t1_latest
        t3_latest = int((m_sub["_tier"] == 3).sum())
        t3_base = int((j_sub["_tier"] == 3).sum()) if len(j_sub) > 0 else t3_latest

        avg_latest = float(m_sub["OVERALL_FIVESTAR"].mean())
        avg_base = float(j_sub["OVERALL_FIVESTAR"].mean()) if len(j_sub) > 0 else avg_latest

        n_stores = len(m_sub)
        n_fran = int(m_sub["CURR_FRAN_OWNER_NM"].nunique())

        t1_pct_chg = ((t1_latest - t1_base) / t1_base * 100) if t1_base > 0 else 0
        t3_pct_chg = ((t3_latest - t3_base) / t3_base * 100) if t3_base > 0 else 0

        oa_list.append({
            "oa": oa,
            "n": n_stores,
            "avg_latest": round(avg_latest, 2),
            "avg_base": round(avg_base, 2),
            "t1_latest": t1_latest,
            "t1_base": t1_base,
            "t3_latest": t3_latest,
            "t3_base": t3_base,
            "delta": round(avg_latest - avg_base, 2),
            "t1_pct_chg": round(t1_pct_chg, 1),
            "t3_pct_chg": round(t3_pct_chg, 1),
        })

    oa_list.sort(key=lambda x: x["avg_latest"], reverse=True)

    # Binding table (national, by tier, May 2026)
    binding_tbl = {}
    for t in [1, 2, 3]:
        sub = may_df[may_df["_tier"] == t]
        binding_tbl[str(t)] = {}
        for col in STAR_COLS:
            cnt = (sub["_binding"] == col).sum()
            pct = round(cnt / len(sub) * 100, 1) if len(sub) > 0 else 0
            binding_tbl[str(t)][col] = pct

    # Correlation: 5-Star vs SSSG/SSTG (all months pooled, Jan-May 2026)
    corr_df = df[["OVERALL_FIVESTAR", "SSSG", "SSTG"]].dropna()
    # Clip extreme outliers (top/bottom 0.5%)
    for col in ["SSSG", "SSTG"]:
        lo, hi = corr_df[col].quantile([0.005, 0.995])
        corr_df[col] = corr_df[col].clip(lo, hi)
    corr_sssg = 0.0
    corr_sstg = 0.0
    if len(corr_df) > 5:
        try:
            corr_sssg = round(pearsonr(corr_df["OVERALL_FIVESTAR"], corr_df["SSSG"])[0], 2)
        except Exception:
            corr_sssg = 0.0
        try:
            corr_sstg = round(pearsonr(corr_df["OVERALL_FIVESTAR"], corr_df["SSTG"])[0], 2)
        except Exception:
            corr_sstg = 0.0

    nat = {
        "n_stores_latest": latest_n,
        "monthly": monthly,
        "startCounts": flows["startCounts"],
        "endCounts": flows["endCounts"],
        "flows": flows["flows"],
        "moved_up": flows["moved_up"],
        "moved_down": flows["moved_down"],
        "tier_story": flows["tier_story"],
        "zone_rank": oa_list,
        "binding_tbl": binding_tbl,
        "corr_fivestar_sssg": corr_sssg,
        "corr_fivestar_sstg": corr_sstg,
    }

    return nat


# ─── Zone Scorecards ───────────────────────────────────────────────────────

def compute_zone_scorecards(df, workshops_by_oa=None):
    """Compute per-OA zone scorecard data."""
    print("Computing zone scorecards...")

    store_df = df  # already has store list info joined

    if workshops_by_oa is None:
        workshops_by_oa = {}

    zones = {}
    for oa in sorted(df["OPX_OA"].dropna().unique()):
        oa_df = df[df["OPX_OA"] == oa]
        oa_workshops = workshops_by_oa.get(oa, {})
        z = compute_single_zone(oa_df, oa_workshops)
        if z:
            zones[oa] = z

    return zones


def compute_single_zone(zone_df, workshops=None):
    """Compute data for a single OA zone."""
    if workshops is None:
        workshops = {}
    oa = zone_df["OPX_OA"].iloc[0]

    may_df = zone_df[zone_df["MONTHNUM"] == 5]
    jan_df = zone_df[zone_df["MONTHNUM"] == 1]

    if len(may_df) == 0:
        return None

    n_stores = len(may_df)
    n_fran = int(may_df["CURR_FRAN_OWNER_NM"].nunique())
    headline_avg = float(may_df["OVERALL_FIVESTAR"].mean())
    base_avg = float(jan_df["OVERALL_FIVESTAR"].mean()) if len(jan_df) > 0 else headline_avg

    # Monthly averages
    monthly = []
    for p in PERIODS:
        m = p % 100
        sub = zone_df[zone_df["MONTHNUM"] == m]
        if len(sub) == 0:
            continue
        monthly.append({
            "period": p,
            "avg": round(float(sub["OVERALL_FIVESTAR"].mean()), 3),
            "n": len(sub),
            "t1": int((sub["_tier"] == 1).sum()),
            "t2": int((sub["_tier"] == 2).sum()),
            "t3": int((sub["_tier"] == 3).sum()),
            "win": round(float(sub["WIN_SCORE_STAR"].mean()), 3) if sub["WIN_SCORE_STAR"].notna().any() else 0,
            "speed": round(float(sub["SPEED_STAR"].mean()), 3) if sub["SPEED_STAR"].notna().any() else 0,
            "fscc": round(float(sub["FSCC_STAR"].mean()), 3) if sub["FSCC_STAR"].notna().any() else 0,
            "brand": round(float(sub["BRAND_STAR"].mean()), 3) if sub["BRAND_STAR"].notna().any() else 0,
            "hb": round(float(sub["HB_ONTIME_STAR"].mean()), 3) if sub["HB_ONTIME_STAR"].notna().any() else 0,
        })

    # Tier flows
    flows = compute_tier_flows(zone_df)

    t1_start = flows["startCounts"].get(1, 0)
    t1_end = flows["endCounts"].get(1, 0)
    t3_start = flows["startCounts"].get(3, 0)
    t3_end = flows["endCounts"].get(3, 0)

    t1_reduction_pct = round((t1_start - t1_end) / t1_start * 100, 1) if t1_start > 0 else 0
    t3_growth_pct = round((t3_end - t3_start) / t3_start * 100, 1) if t3_start > 0 else 0

    # Binding table by tier (May 2026)
    binding_tbl = {}
    for t in [1, 2, 3]:
        sub = may_df[may_df["_tier"] == t]
        binding_tbl[str(t)] = {}
        for col in STAR_COLS:
            cnt = (sub["_binding"] == col).sum()
            pct = round(cnt / len(sub) * 100, 1) if len(sub) > 0 else 0
            binding_tbl[str(t)][col] = pct

    # Avg by tier (May 2026)
    avg_by_tier = []
    for t in [1, 2, 3]:
        sub = may_df[may_df["_tier"] == t]
        if len(sub) > 0:
            avg_by_tier.append({
                "tier": t,
                "avg": round(float(sub["OVERALL_FIVESTAR"].mean()), 2),
                "n": len(sub),
            })

    # Bootcamp areas (Tier 1 areas for targeting - all areas in zone with Tier 1 stores)
    bootcamp_data = []
    if len(may_df) > 0:
        area_groups = may_df.groupby(["FAREADESC", "NIELSENDMADESC", "CURR_FRAN_OWNER_NM"])
        for (area, dma, fran), grp in area_groups:
            n_t1 = int((grp["_tier"] == 1).sum())
            if n_t1 == 0:
                continue
            total = len(grp)
            rate = round(n_t1 / total * 100, 0) if total > 0 else 0
            # Compute binding breakdown for this group's Tier 1 stores
            t1_sub = grp[grp["_tier"] == 1]
            n_t1_total = len(t1_sub)
            win_pct = round((t1_sub["_binding"] == "WIN_SCORE_STAR").sum() / n_t1_total * 100) if n_t1_total > 0 else 0
            speed_pct = round((t1_sub["_binding"] == "SPEED_STAR").sum() / n_t1_total * 100) if n_t1_total > 0 else 0
            hb_pct = round((t1_sub["_binding"] == "HB_ONTIME_STAR").sum() / n_t1_total * 100) if n_t1_total > 0 else 0
            brand_pct = round((t1_sub["_binding"] == "BRAND_STAR").sum() / n_t1_total * 100) if n_t1_total > 0 else 0
            fscc_pct = round((t1_sub["_binding"] == "FSCC_STAR").sum() / n_t1_total * 100) if n_t1_total > 0 else 0

            bootcamp_data.append({
                "FAREADESC": area if pd.notna(area) else "Unknown",
                "dma": dma if pd.notna(dma) else "Unknown",
                "fran": fran if pd.notna(fran) else "Unknown",
                "n_t1": n_t1,
                "total": total,
                "rate": int(rate),
                "win_pct": win_pct,
                "speed_pct": speed_pct,
                "hb_pct": hb_pct,
                "brand_pct": brand_pct,
                "fscc_pct": fscc_pct,
            })
    bootcamp_data.sort(key=lambda x: x["n_t1"], reverse=True)

    # Area spotlight (lowest and highest scoring areas with 5+ stores)
    area_avgs = may_df.groupby("FAREADESC").agg(
        n=("CHAINED_STORE_ID", "count"),
        avg=("OVERALL_FIVESTAR", "mean")
    ).reset_index()
    area_avgs = area_avgs[area_avgs["n"] >= 5].sort_values("avg", ascending=True)
    low_areas = area_avgs.head(10).to_dict("records")
    high_areas = area_avgs.tail(10).sort_values("avg", ascending=False).head(10).to_dict("records")

    for lst in [low_areas, high_areas]:
        for r in lst:
            r["n"] = int(r["n"])
            r["avg"] = round(float(r["avg"]), 2)

    # Franchisee spotlight
    fran_avgs = may_df.groupby("CURR_FRAN_OWNER_NM").agg(
        n=("CHAINED_STORE_ID", "count"),
        avg=("OVERALL_FIVESTAR", "mean")
    ).reset_index()
    fran_avgs = fran_avgs[fran_avgs["n"] >= 3].sort_values("avg", ascending=True)
    low_fran = fran_avgs.head(3).to_dict("records") if len(fran_avgs) > 0 else []
    high_fran = fran_avgs.tail(3).sort_values("avg", ascending=False).head(3).to_dict("records") if len(fran_avgs) > 0 else []
    for lst in [low_fran, high_fran]:
        for r in lst:
            r["n"] = int(r["n"])
            r["avg"] = round(float(r["avg"]), 2)

    # Per-store detail for the "Portfolio" tab
    store_ids = may_df["CHAINED_STORE_ID"].unique()
    stores_data = []
    for sid in store_ids:
        store_months = zone_df[zone_df["CHAINED_STORE_ID"] == sid]
        if len(store_months) == 0:
            continue
        latest = store_months.iloc[-1]

        scores = {}
        for m in PERIOD_MONTHS:
            sub = store_months[store_months["MONTHNUM"] == m]
            if len(sub) > 0 and pd.notna(sub["OVERALL_FIVESTAR"].iloc[0]):
                scores[m] = round(float(sub["OVERALL_FIVESTAR"].iloc[0]), 2)

        if len(scores) == 0:
            continue

        q1_vals = [scores[m] for m in [1, 2, 3] if m in scores]
        q2_vals = [scores[m] for m in [4, 5, 6] if m in scores]
        q1_avg = round(sum(q1_vals) / len(q1_vals), 2) if q1_vals else None
        q2_avg = round(sum(q2_vals) / len(q2_vals), 2) if q2_vals else None
        all_vals = list(scores.values())
        ytd_avg = round(sum(all_vals) / len(all_vals), 2)

        # Trend slope (linear regression)
        if len(all_vals) >= 3:
            xs = list(range(len(all_vals)))
            n = len(xs)
            sx = sum(xs)
            sy = sum(all_vals)
            sxx = sum(x * x for x in xs)
            sxy = sum(xs[i] * all_vals[i] for i in range(n))
            denom = n * sxx - sx * sx
            slope = (n * sxy - sx * sy) / denom if denom != 0 else 0
        else:
            slope = 0

        area = latest.get("FAREADESC", "")
        if pd.isna(area):
            area = ""
        fran = latest.get("CURR_FRAN_OWNER_NM", "")
        if pd.isna(fran):
            fran = ""
        dma = latest.get("NIELSENDMADESC", "")
        if pd.isna(dma):
            dma = ""
        fop = latest.get("FOP", "")
        if pd.isna(fop):
            fop = "Unknown"
        director = latest.get("DIRECTOR", "")
        if pd.isna(director):
            director = "Unknown"

        # Component scores per month
        comps = {}
        for comp in STAR_COLS:
            vals = []
            for m in PERIOD_MONTHS:
                sub = store_months[store_months["MONTHNUM"] == m]
                if len(sub) > 0 and pd.notna(sub[comp].iloc[0]):
                    vals.append(round(float(sub[comp].iloc[0]), 2))
                else:
                    vals.append(None)
            comps[comp] = vals

        # Format store ID: pad to 5 digits
        sid_str = str(int(sid)) if isinstance(sid, float) else str(sid)
        if len(sid_str) < 5 and sid_str.isdigit():
            sid_str = sid_str.zfill(5)

        # — Status flags (defaulting / at-risk / T1 watch) —
        reversed_months = sorted(scores.keys(), reverse=True)
        cons_under = 0
        for m in reversed_months:
            v = scores.get(m)
            if v is not None and v < DEFAULT_THRESHOLD:
                cons_under += 1
            else:
                break

        total_under = sum(1 for m in scores if scores[m] is not None and scores[m] < DEFAULT_THRESHOLD)

        dl = cons_under >= 3 or total_under >= 4
        ar = cons_under == 2 and not dl
        latest_month = max(scores.keys()) if scores else 0
        latest_score = scores.get(latest_month)
        tw = not dl and not ar and latest_score is not None and DEFAULT_THRESHOLD <= latest_score < TIER_THRESHOLD

        if dl:
            st = "dl"
        elif ar:
            st = "ar"
        elif tw:
            st = "tw"
        else:
            st = "ok"

        # FSCC failure count (proxy: component score < 2.0)
        fscc_fails = sum(1 for v in comps.get("FSCC_STAR", []) if v is not None and v < DEFAULT_THRESHOLD)
        brand_fails = sum(1 for v in comps.get("BRAND_STAR", []) if v is not None and v < DEFAULT_THRESHOLD)

        entry = {
            "s": sid_str,
            "a": str(area),
            "f": str(fran),
            "d": str(dma),
            "o": str(fop),
            "r": str(director),
            "q1": q1_avg,
            "q2": q2_avg,
            "y": ytd_avg,
            "t": round(slope, 3),
            "cw": comps["WIN_SCORE_STAR"],
            "cs": comps["SPEED_STAR"],
            "cb": comps["BRAND_STAR"],
            "ch": comps["HB_ONTIME_STAR"],
            "cf": comps["FSCC_STAR"],
            "st": st,
            "cu": cons_under,
            "fscc": fscc_fails,
            "brand": brand_fails,
        }
        # Add monthly scores as m1..mN
        for m in PERIOD_MONTHS:
            entry[f"m{m}"] = scores.get(m)
        stores_data.append(entry)

    # — Default Watch list —
    # Collect: all defaulting → all at-risk → all T1 watch, sorted by severity
    status_rank = {"dl": 0, "ar": 1, "tw": 2, "ok": 3}
    watch_stores = sorted(stores_data, key=lambda s: (status_rank.get(s["st"], 9), s["y"] if s["y"] is not None else 99))
    default_watch = []
    for s in watch_stores[:25]:
        binding = get_binding_for_store(sid=s["s"], zone_df=zone_df)
        latest_month_key = f"m{PERIOD_MONTHS[-1]}" if PERIOD_MONTHS else "m5"
        default_watch.append({
            "s": s["s"],
            "a": s["a"],
            "f": s["f"],
            "o": s["o"],
            "sc": s["y"] if s["y"] is not None else s.get(latest_month_key),
            "st": s["st"],
            "cu": s["cu"],
            "fscc": s["fscc"],
            "brand": s["brand"],
            "binding": binding,
        })

    # OA-level aggregations
    n_defaulting = sum(1 for s in stores_data if s["st"] == "dl")
    n_at_risk = sum(1 for s in stores_data if s["st"] == "ar")
    n_t1_watch = sum(1 for s in stores_data if s["st"] == "tw")

    # Best improvers (first -> last month delta)
    first_m = PERIOD_MONTHS[0] if PERIOD_MONTHS else 1
    last_m = PERIOD_MONTHS[-1] if PERIOD_MONTHS else 5
    first_df = zone_df[zone_df["MONTHNUM"] == first_m]
    last_df = zone_df[zone_df["MONTHNUM"] == last_m]
    if len(first_df) > 0 and len(last_df) > 0:
        jan_may = first_df[["CHAINED_STORE_ID", "OVERALL_FIVESTAR"]].merge(
            last_df[["CHAINED_STORE_ID", "OVERALL_FIVESTAR"]],
            on="CHAINED_STORE_ID",
            suffixes=("_first", "_last")
        )
        jan_may["delta"] = jan_may["OVERALL_FIVESTAR_last"] - jan_may["OVERALL_FIVESTAR_first"]
        best_improvers = jan_may.nlargest(10, "delta")[
            ["CHAINED_STORE_ID", "OVERALL_FIVESTAR_first", "OVERALL_FIVESTAR_last", "delta"]
        ].to_dict("records")
    else:
        best_improvers = []
    for r in best_improvers:
        r["s"] = round(float(r.pop("OVERALL_FIVESTAR_first")), 2)
        r["e"] = round(float(r.pop("OVERALL_FIVESTAR_last")), 2)
        sid_b = str(r["CHAINED_STORE_ID"]).rstrip(".0")
        if len(sid_b) < 5 and sid_b.isdigit():
            sid_b = sid_b.zfill(5)
        r["CHAINED_STORE_ID"] = sid_b
        r["delta"] = round(float(r["delta"]), 2)

    return {
        "oa": oa,
        "n_stores": n_stores,
        "n_fran": n_fran,
        "headline_avg": round(headline_avg, 2),
        "base_avg": round(base_avg, 2),
        "monthly": monthly,
        "startCounts": flows["startCounts"],
        "endCounts": flows["endCounts"],
        "flows": flows["flows"],
        "moved_up": flows["moved_up"],
        "moved_down": flows["moved_down"],
        "t1_reduction_pct": t1_reduction_pct,
        "t3_growth_pct": t3_growth_pct,
        "tier_story": flows["tier_story"],
        "binding_tbl": binding_tbl,
        "avg_by_tier": avg_by_tier,
        "bootcamp_areas": bootcamp_data,
        "low_areas": low_areas,
        "high_areas": high_areas,
        "low_fran": low_fran,
        "high_fran": high_fran,
        "default_watch": default_watch,
        "best_improvers": best_improvers,
        "stores": stores_data,
        "n_defaulting": n_defaulting,
        "n_at_risk": n_at_risk,
        "n_t1_watch": n_t1_watch,
        "workshops": workshops,
    }


# ─── FOP Dashboard ─────────────────────────────────────────────────────────

def compute_fop_data(df, zones_data):
    """Compute FOP-level data aggregated from zones_data stores.

    Groups stores by FOP → Franchisee, computing summary counts and
    per-store detail for the FOP Dashboard.
    """
    print("Computing FOP dashboard data...")

    # Collect all stores with FOP from all zones
    all_stores = []
    for oa, z in zones_data.items():
        for s in z.get("stores", []):
            all_stores.append(s)

    if not all_stores:
        print("  No stores found for FOP data")
        return {}

    # Group by Director → FOP → Franchisee
    director_fops = {}  # director -> set of fops
    fop_groups = {}
    fop_director = {}  # fop -> director
    for s in all_stores:
        fop = s.get("o", "Unknown")
        fran = s.get("f", "Unknown")
        director = s.get("r", "Unknown")
        fop_director[fop] = director
        if director not in director_fops:
            director_fops[director] = set()
        director_fops[director].add(fop)
        if fop not in fop_groups:
            fop_groups[fop] = {}
        if fran not in fop_groups[fop]:
            fop_groups[fop][fran] = []
        fop_groups[fop][fran].append(s)

    # Director-level aggregations
    director_data = {}
    for director, fops in director_fops.items():
        dir_stores = [s for s in all_stores if s.get("r", "Unknown") == director]
        dir_n_dl = sum(1 for s in dir_stores if s.get("st") == "dl")
        dir_n_ar = sum(1 for s in dir_stores if s.get("st") == "ar")
        dir_n_tw = sum(1 for s in dir_stores if s.get("st") == "tw")
        dir_n_fran = len(set(s.get("f", "Unknown") for s in dir_stores))
        director_data[director] = {
            "director": director,
            "n_stores": len(dir_stores),
            "n_fran": dir_n_fran,
            "n_defaulting": dir_n_dl,
            "n_at_risk": dir_n_ar,
            "n_t1_watch": dir_n_tw,
            "fops": sorted(fops),
        }

    fop_data = {}
    for fop in sorted(fop_groups.keys()):
        fran_list = []
        n_stores_total = 0
        n_defaulting = 0
        n_at_risk = 0
        n_t1_watch = 0
        sum_avg = 0.0
        count_avg = 0

        for fran in sorted(fop_groups[fop].keys()):
            stores = fop_groups[fop][fran]
            fran_avg = sum(s.get("y") or s.get("m5") or 0 for s in stores) / len(stores)
            fran_dl = sum(1 for s in stores if s.get("st") == "dl")
            fran_ar = sum(1 for s in stores if s.get("st") == "ar")
            fran_tw = sum(1 for s in stores if s.get("st") == "tw")

            n_stores_total += len(stores)
            n_defaulting += fran_dl
            n_at_risk += fran_ar
            n_t1_watch += fran_tw
            sum_avg += fran_avg
            count_avg += 1

            fran_list.append({
                "fran": fran,
                "n": len(stores),
                "avg": round(fran_avg, 2),
                "n_defaulting": fran_dl,
                "n_at_risk": fran_ar,
                "n_t1_watch": fran_tw,
                "stores": [{
                    "s": s["s"],
                    "m1": s.get("m1"),
                    "m2": s.get("m2"),
                    "m3": s.get("m3"),
                    "m4": s.get("m4"),
                    "m5": s.get("m5"),
                    "y": s.get("y"),
                    "t": s.get("t", 0),
                    "st": s.get("st", "ok"),
                    "cu": s.get("cu", 0),
                    "fscc": s.get("fscc", 0),
                    "brand": s.get("brand", 0),
                    "d": s.get("d", ""),
                    "a": s.get("a", ""),
                    "oa": s.get("o", ""),
                    "cw": s.get("cw", []),
                    "cs": s.get("cs", []),
                    "cb": s.get("cb", []),
                    "ch": s.get("ch", []),
                    "cf": s.get("cf", []),
                } for s in stores]
            })

        # Sort franchisees by defaulting count (desc), then at-risk, then watch
        fran_list.sort(key=lambda x: (-x["n_defaulting"], -x["n_at_risk"], -x["n_t1_watch"]))

        overall_avg = round(sum_avg / count_avg, 2) if count_avg > 0 else 0

        fop_data[fop] = {
            "fop": fop,
            "director": fop_director.get(fop, "Unknown"),
            "n_stores": n_stores_total,
            "n_fran": len(fran_list),
            "n_defaulting": n_defaulting,
            "n_at_risk": n_at_risk,
            "n_t1_watch": n_t1_watch,
            "headline_avg": overall_avg,
            "franchisees": fran_list,
        }

    print(f"  {len(fop_data)} FOPs across {len(director_data)} directors, "
          f"{sum(v['n_fran'] for v in fop_data.values())} franchisees")
    return {"fops": fop_data, "directors": sorted(director_data.keys()),
            "directorData": director_data}


# ─── LLM Summaries ─────────────────────────────────────────────────────────

def cleanup_session(session_id, headers):
    try:
        req = urllib.request.Request(
            f"{OPENCODE_SERVER_URL}/session/{session_id}",
            method="DELETE",
            headers=headers,
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def call_opencode_server(prompt_parts, system_prompt=None, max_tokens=2000):
    """Send a prompt to the opencode server and return the text response."""
    if not OPENCODE_SERVER_PASS:
        print("  WARNING: OPENCODE_SERVER_PASSWORD not set, skipping LLM summaries")
        return None

    auth_str = base64.b64encode(f"{OPENCODE_SERVER_USER}:{OPENCODE_SERVER_PASS}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_str}",
        "Content-Type": "application/json",
    }

    full_prompt = "\n".join(prompt_parts)

    # Create session
    req = urllib.request.Request(
        f"{OPENCODE_SERVER_URL}/session",
        data=json.dumps({"title": "5-Star OA Summaries"}).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_LLM_TIMEOUT) as resp:
            session = json.loads(resp.read())
    except Exception as e:
        print(f"    Could not create session: {e}")
        return None

    session_id = session["id"]

    # Build message body — let the model use its default
    body = {
        "parts": [{"type": "text", "text": full_prompt}],
    }
    if system_prompt:
        body["system"] = system_prompt

    req2 = urllib.request.Request(
        f"{OPENCODE_SERVER_URL}/session/{session_id}/message",
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req2, timeout=_LLM_TIMEOUT) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        print(f"    LLM request failed: {e}")
        cleanup_session(session_id, headers)
        return None

    # Extract text response
    try:
        for part in result.get("parts", []):
            if part.get("type") == "text":
                text = part["text"]
                # Try to extract JSON from the text (```json ... ``` or bare {...})
                json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(1))
                    cleanup_session(session_id, headers)
                    return parsed
                # Try bare JSON object
                json_match = re.search(r"\{.*\}", text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    cleanup_session(session_id, headers)
                    return parsed
                return None
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"    Could not parse LLM response: {e}")
    finally:
        cleanup_session(session_id, headers)
    return None


def _summary_version():
    """Return a version string that changes when the month range changes."""
    m_str = "-".join(str(m) for m in PERIOD_MONTHS) if PERIOD_MONTHS else "1-5"
    return f"months_{len(PERIOD_MONTHS)}_{m_str}"


def summarize_zones(zones_data):
    """Generate LLM summaries for each OA zone using the opencode server."""
    oa_names = sorted(zones_data.keys())
    version = _summary_version()

    # Check cache
    cache = {}
    if SUMMARIES_CACHE.exists():
        try:
            with open(SUMMARIES_CACHE, "r") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            cache = {}

    # Helper to apply cached summaries
    def _apply_cached():
        for oa in oa_names:
            if oa in cache:
                zones_data[oa]["summary"] = cache[oa]

    # Check if all OAs have cached summaries AND version matches
    if cache.get("_version") == version and all(oa in cache for oa in oa_names):
        print("  Using cached LLM summaries")
        _apply_cached()
        return

    # Check if we have any cached summaries at all (even stale)
    has_any_cache = any(oa in cache for oa in oa_names)

    # If no password configured, skip LLM and use whatever cache exists
    if not OPENCODE_SERVER_PASS:
        if has_any_cache:
            print("  Using cached LLM summaries (no server configured)")
            _apply_cached()
            return
        print("  No LLM server configured and no cached summaries")
        return

    print("  Generating LLM summaries...")

    # Build compact OA data for the prompt
    oa_data = {}
    for oa in oa_names:
        z = zones_data[oa]
        bind_t1 = z.get("binding_tbl", {}).get("1", {})
        bind_t2 = z.get("binding_tbl", {}).get("2", {})
        top_bind_t1 = sorted(bind_t1.items(), key=lambda x: -x[1])[:2]
        top_bind_t2 = sorted(bind_t2.items(), key=lambda x: -x[1])[:2]
        bootcamp = z.get("bootcamp_areas", [])
        low_areas = z.get("low_areas", [])
        high_areas = z.get("high_areas", [])
        improvers = z.get("best_improvers", [])

        # Compact trend: monthly average scores only
        monthly_avgs = [
            {"period": m.get("period", ""), "avg": round(m.get("avg", 0), 2)}
            for m in (z.get("monthly") or [])
        ]
        oa_data[oa] = {
            "stores": z["n_stores"],
            "fran": z["n_fran"],
            "avg_by_tier": z["avg_by_tier"],
            "monthly_avgs": monthly_avgs,
            "tier_start": z["startCounts"],
            "tier_end": z["endCounts"],
            "moved_up": z["moved_up"],
            "moved_down": z["moved_down"],
            "t3_growth_pct": z["t3_growth_pct"],
            "t1_reduction_pct": z["t1_reduction_pct"],
            "tier_story": z.get("tier_story", ""),
            "bind_t1": {k: v for k, v in top_bind_t1},
            "bind_t2": {k: v for k, v in top_bind_t2},
            "t1_hotspots": [
                {"area": a["FAREADESC"], "t1_stores": a["n_t1"], "rate": a["rate"]}
                for a in bootcamp[:3]
            ],
            "low_areas": [
                {"area": a["FAREADESC"], "avg_score": a["avg"]} for a in low_areas[:3]
            ],
            "high_areas": [
                {"area": a["FAREADESC"], "avg_score": a["avg"]} for a in high_areas[:3]
            ],
            "top_improvers": [
                {"store": i["CHAINED_STORE_ID"], "delta": i["delta"]}
                for i in improvers[:3]
            ],
            "at_risk_stores": z["n_at_risk"],
            "defaulting_stores": z["n_defaulting"],
            "t1_watch_stores": z["n_t1_watch"],
        }

    system_prompt = (
        "You are a 5-Star operations analyst for a major pizza chain. "
        "Write a structured 3-paragraph summary for each OA zone. "
        "Paragraph 1 — PAST: What happened over the period. How many stores moved up vs down in tiers, "
        "what drove the movement (which metrics were binding). Use specific numbers. "
        "Paragraph 2 — PRESENT: Current state of the portfolio. Overall average, tier distribution, "
        "hotspots (areas with the most Tier 1 stores), risk counts (defaulting, at-risk, T1 watch), "
        "and the biggest binding constraint holding the zone back. "
        "Paragraph 3 — FUTURE: The single most important action the OA should take, and where to focus "
        "(specific areas or franchisees). "
        "Be direct and operational — use specific numbers. This is for OAs who know their business."
    )

    period_label = get_period_label()
    user_prompt = (
        f"Here is the {period_label} 5-Star data for all OAs:\n\n"
        + json.dumps(oa_data, indent=2)
        + "\n\nReturn a JSON object with a 'summaries' key mapping each OA name "
        "to a 3-paragraph summary (PAST | PRESENT | FUTURE)."
    )

    result = call_opencode_server([user_prompt], system_prompt=system_prompt)
    if result is None:
        if has_any_cache:
            print("  LLM call failed, falling back to cached summaries (stale)")
            _apply_cached()
            return
        print("  LLM call failed, no cached summaries available")
        return

    summaries = result.get("summaries", {})
    for oa in oa_names:
        summary = summaries.get(oa, "")
        if summary:
            zones_data[oa]["summary"] = summary
            cache[oa] = summary

    # Write cache
    cache["_version"] = version
    try:
        with open(SUMMARIES_CACHE, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"  Cached {len(summaries)} summaries to {SUMMARIES_CACHE.name}")
    except IOError as e:
        print(f"  Could not write cache: {e}")


def summarize_leadership(nat_data):
    """Generate a national leadership LLM summary using the opencode server."""
    version = _summary_version()
    cache = {}
    if SUMMARIES_CACHE.exists():
        try:
            with open(SUMMARIES_CACHE, "r") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            cache = {}

    # Cache keys
    VER_KEY = "_leadership_version"
    SUM_KEY = "_leadership_summary"

    if cache.get(VER_KEY) == version and SUM_KEY in cache:
        print("  Using cached leadership summary")
        nat_data["summary"] = cache[SUM_KEY]
        return

    if not OPENCODE_SERVER_PASS:
        if SUM_KEY in cache:
            print("  Using cached leadership summary (no server)")
            nat_data["summary"] = cache[SUM_KEY]
            return
        print("  No LLM server configured and no cached leadership summary")
        return

    print("  Generating leadership summary...")

    m_avgs = [{"period": m.get("period", ""), "avg": round(m.get("avg", 0), 2),
               "t1": m.get("t1", 0), "t2": m.get("t2", 0), "t3": m.get("t3", 0),
               "win": round(m.get("win", 0), 2), "speed": round(m.get("speed", 0), 2),
               "fscc": round(m.get("fscc", 0), 2), "brand": round(m.get("brand", 0), 2),
               "hb": round(m.get("hb", 0), 2)}
              for m in (nat_data.get("monthly") or [])]

    zone_rank_compact = [
        {"oa": z["oa"], "stores": z["n"], "avg": z["avg_latest"],
         "delta": round(z["delta"], 2), "t1": z["t1_latest"], "t3": z["t3_latest"],
         "t1_chg_pct": z["t1_pct_chg"], "t3_chg_pct": z["t3_pct_chg"]}
        for z in (nat_data.get("zone_rank") or [])
    ]

    leadership_data = {
        "n_stores": nat_data.get("n_stores_latest", 0),
        "monthly_trend": m_avgs,
        "startCounts": nat_data.get("startCounts", {}),
        "endCounts": nat_data.get("endCounts", {}),
        "moved_up": nat_data.get("moved_up", 0),
        "moved_down": nat_data.get("moved_down", 0),
        "tier_story": nat_data.get("tier_story", []),
        "zone_rank": zone_rank_compact,
        "binding_tbl": nat_data.get("binding_tbl", {}),
        "corr_fivestar_sssg": nat_data.get("corr_fivestar_sssg"),
        "corr_fivestar_sstg": nat_data.get("corr_fivestar_sstg"),
        "n_defaulting": nat_data.get("n_defaulting", 0),
        "n_at_risk": nat_data.get("n_at_risk", 0),
        "n_t1_watch": nat_data.get("n_t1_watch", 0),
    }

    system_prompt = (
        "You are a 5-Star operations analyst for a major pizza chain. "
        "Write a concise national narrative summary for leadership. "
        "No headings, no sections — just a flowing narrative that covers: "
        "the national trend over the period (overall average, tier movement, which zones improved most/least, "
        "which components drove the movement), the current state of the portfolio (average, tier distribution, "
        "zones needing attention, binding constraints by tier, risk counts), "
        "and the top national priority with operational focus areas. "
        "Use specific numbers throughout. Be direct and operational. "
        "This is for senior leadership — 3-4 paragraphs, no section labels."
    )

    period_label = get_period_label()
    user_prompt = (
        f"Here is the {period_label} national 5-Star data:\n\n"
        + json.dumps(leadership_data, indent=2)
        + "\n\nReturn a JSON object with a single key 'summary' containing "
        "a national leadership narrative (no section headings, just flowing text)."
    )

    result = call_opencode_server([user_prompt], system_prompt=system_prompt)
    if result is None:
        if SUM_KEY in cache:
            print("  LLM call failed, falling back to cached leadership summary")
            nat_data["summary"] = cache[SUM_KEY]
            return
        print("  LLM call failed, no cached leadership summary")
        return

    summary = result.get("summary", "")
    if summary:
        nat_data["summary"] = summary
        cache[SUM_KEY] = summary
        cache[VER_KEY] = version
        try:
            with open(SUMMARIES_CACHE, "w") as f:
                json.dump(cache, f, indent=2)
            print(f"  Cached leadership summary")
        except IOError as e:
            print(f"  Could not write cache: {e}")
    else:
        print("  Empty leadership summary returned")


def summarize_fops(fop_data):
    """Generate LLM summaries for each FOP using the opencode server."""
    fop_names = sorted(fop_data.get("fops", {}).keys())
    version = _summary_version()

    cache = {}
    if SUMMARIES_CACHE.exists():
        try:
            with open(SUMMARIES_CACHE, "r") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            cache = {}

    def _apply_cached():
        for name in fop_names:
            d = fop_data.get("fops", {}).get(name)
            if d and name in cache:
                d["summary"] = cache[name]

    fp_key = f"_fop_version_{version}"
    if cache.get(fp_key) == version and all(name in cache for name in fop_names):
        print("  Using cached FOP summaries")
        _apply_cached()
        return

    has_any_cache = any(name in cache for name in fop_names)

    if not OPENCODE_SERVER_PASS:
        if has_any_cache:
            print("  Using cached FOP summaries (no server)")
            _apply_cached()
            return
        print("  No LLM server configured and no cached FOP summaries")
        return

    print("  Generating FOP summaries...")

    # Build per-FOP compact data
    fop_data_compact = {}
    for name in fop_names:
        fop = fop_data.get("fops", {}).get(name, {})
        # Collect franchisee summaries for this FOP
        fran_compact = []
        for fr in (fop.get("franchisees") or []):
            fran_compact.append({
                "name": fr.get("fran", ""),
                "n_stores": fr.get("n", 0),
                "avg": round(fr.get("avg", 0), 2),
                "n_defaulting": fr.get("n_defaulting", 0),
                "n_at_risk": fr.get("n_at_risk", 0),
                "n_t1_watch": fr.get("n_t1_watch", 0),
            })
        fop_data_compact[name] = {
            "fop": name,
            "director": fop.get("director", ""),
            "n_stores": fop.get("n_stores", 0),
            "n_fran": fop.get("n_fran", 0),
            "headline_avg": round(fop.get("headline_avg", 0), 2),
            "n_defaulting": fop.get("n_defaulting", 0),
            "n_at_risk": fop.get("n_at_risk", 0),
            "n_t1_watch": fop.get("n_t1_watch", 0),
            "franchisees": fran_compact,
        }

    system_prompt = (
        "You are a 5-Star operations analyst for a major pizza chain. "
        "Write a structured 3-paragraph summary for each FOP (Franchise Operator Partner). "
        "Paragraph 1 — PAST: What happened over the period. How the franchisee portfolio shifted, "
        "which franchisees improved or declined, risk count changes. Use specific numbers. "
        "Paragraph 2 — PRESENT: Current state of the FOP's portfolio. Overall average, franchisee distribution, "
        "risk counts (defaulting, at-risk, T1 watch), and the biggest challenges. "
        "Paragraph 3 — FUTURE: The single most important action this FOP should take, "
        "and which franchisees need the most support. Be direct and operational."
    )

    period_label = get_period_label()
    user_prompt = (
        f"Here is the {period_label} 5-Star data for all FOPs:\n\n"
        + json.dumps(fop_data_compact, indent=2)
        + "\n\nReturn a JSON object with a 'summaries' key mapping each FOP name "
        "to a 3-paragraph summary (PAST | PRESENT | FUTURE)."
    )

    result = call_opencode_server([user_prompt], system_prompt=system_prompt)
    if result is None:
        if has_any_cache:
            print("  LLM call failed, falling back to cached FOP summaries (stale)")
            _apply_cached()
            return
        print("  LLM call failed, no cached FOP summaries")
        return

    summaries = result.get("summaries", {})
    for name in fop_names:
        d = fop_data.get("fops", {}).get(name)
        summary = summaries.get(name, "")
        if summary and d:
            d["summary"] = summary
            cache[name] = summary

    cache[fp_key] = version
    try:
        with open(SUMMARIES_CACHE, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"  Cached {len(summaries)} FOP summaries")
    except IOError as e:
        print(f"  Could not write cache: {e}")


# ─── Snowflake Integration ──────────────────────────────────────────────────

def query_snowflake(sql, params=None):
    """Execute a query against Snowflake and return results as a list of dicts.
    Returns None if Snowflake is not configured or the connector is missing.
    """
    if not SNOWFLAKE_ENABLED:
        print("  Snowflake not configured (set SNOWFLAKE_ACCOUNT/USER/PASSWORD)")
        return None
    if not HAS_SNOWFLAKE:
        print("  snowflake-connector-python not installed; run: pip install snowflake-connector-python")
        return None

    try:
        conn = snowflake.connector.connect(
            account=SNOWFLAKE_ACCOUNT,
            user=SNOWFLAKE_USER,
            password=SNOWFLAKE_PASSWORD,
            warehouse=SNOWFLAKE_WAREHOUSE or None,
            database=SNOWFLAKE_DATABASE or None,
            schema=SNOWFLAKE_SCHEMA or None,
        )
        cur = conn.cursor()
        cur.execute(sql, params or [])
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        result = [dict(zip(cols, row)) for row in rows]
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print(f"  Snowflake query failed: {e}")
        return None


def enrich_with_snowflake(df):
    """Enrich store-month data with actual FSCC visit results from Snowflake.
    Falls back gracefully if Snowflake is unavailable.
    """
    if not SNOWFLAKE_ENABLED:
        return df

    print("  Enriching with Snowflake data...")

    # TODO: Replace with actual SQL when provided by the user.
    # Expected shape: store_id, visit_date, component ('FSCC' or 'BRAND'), result (pass/fail/underperforming)
    # For now this is a placeholder that returns the data unchanged.
    sql = """
    SELECT
        CHAINED_STORE_ID AS store_id,
        VISIT_DATE AS visit_date,
        COMPONENT AS component,
        RESULT AS result
    FROM FIVESTAR_VISITS
    WHERE VISIT_DATE >= '2026-01-01' AND VISIT_DATE < '2026-06-01'
      AND COMPONENT IN ('FSCC', 'BRAND')
    ORDER BY VISIT_DATE
    """
    visit_data = query_snowflake(sql)
    if visit_data is None:
        print("  (proceeding without Snowflake enrichment)")
        return df

    # Convert visit data to a lookup: store_id -> [(date, component, result), ...]
    visit_lookup = {}
    for row in visit_data:
        sid = str(row.get("store_id", "")).strip()
        if not sid:
            continue
        visit_lookup.setdefault(sid, []).append({
            "date": row.get("visit_date"),
            "component": row.get("component"),
            "result": row.get("result"),
        })

    # For each store-month row, look up the most recent visit result for each component
    # and add it as extra columns (_fscc_visit, _brand_visit)
    df["_fscc_visit"] = None
    df["_brand_visit"] = None

    for idx, row in df.iterrows():
        sid = str(row["CHAINED_STORE_ID"]).strip()
        monthnum = int(row["MONTHNUM"])
        # Approximate month-end date for matching
        month_end = f"2026-{monthnum:02d}-01"

        visits = visit_lookup.get(sid, [])
        for v in visits:
            if str(v["date"])[:7] >= month_end[:7]:
                continue  # visit after this month, skip
            if v["component"] == "FSCC":
                df.at[idx, "_fscc_visit"] = v["result"]
            elif v["component"] == "BRAND":
                df.at[idx, "_brand_visit"] = v["result"]

    print(f"  Enriched {len(visit_data)} visits across {len(visit_lookup)} stores")
    return df


# ─── HTML Rendering ────────────────────────────────────────────────────────

def get_month_labels_js():
    """Build a JavaScript array of month labels from PERIOD_MONTHS."""
    labels = json.dumps(MONTH_LABELS)
    return f"const MONTHS = {labels};"

def get_period_label():
    """Build a human-readable period label like 'Jan – Jun 2026'."""
    if len(MONTH_LABELS) >= 2:
        return f"{MONTH_LABELS[0]} – {MONTH_LABELS[-1]} 2026"
    elif MONTH_LABELS:
        return f"{MONTH_LABELS[0]} 2026"
    return "Jan – May 2026"


def replace_data_block(html, var_name, json_data, indent=0):
    """Replace a JavaScript variable assignment with new JSON data.
    Uses a marker/position-based approach to avoid regex issues with nested JSON.
    """
    json_str = json.dumps(json_data, default=safe_json, separators=(",", ":"))

    marker = f"const {var_name} = "
    start = html.find(marker)
    if start < 0:
        print(f"  WARNING: Could not find '{var_name}' in template")
        return html

    # Find the semicolon that ends this const statement
    # Scan forward from the start of the value, tracking brace/bracket depth
    pos = start + len(marker)
    depth_obj = 0
    depth_arr = 0
    in_str = False
    escape = False
    while pos < len(html):
        ch = html[pos]
        if escape:
            escape = False
        elif ch == "\\" and in_str:
            escape = True
        elif ch == '"' and not escape:
            in_str = not in_str
        elif not in_str:
            if ch == "{":
                depth_obj += 1
            elif ch == "}":
                depth_obj -= 1
            elif ch == "[":
                depth_arr += 1
            elif ch == "]":
                depth_arr -= 1
            elif ch == ";" and depth_obj == 0 and depth_arr == 0:
                break
        pos += 1

    if pos >= len(html):
        # Fallback: use regex
        pattern = rf'(const\s+{var_name}\s*=\s*).*?;(\s*//.*)?$'
        new_html = re.sub(pattern, rf'\1{json_str};', html, count=1, flags=re.DOTALL | re.MULTILINE)
        if new_html == html:
            print(f"  WARNING: Could not find '{var_name}' in template")
        return new_html

    new_html = html[:start] + marker + json_str + ";" + html[pos + 1:]
    return new_html


def _replace_month_refs(html):
    """Replace all hardcoded month references with dynamic labels."""
    if not MONTH_LABELS:
        return html
    period_label = get_period_label()
    first_lbl = MONTH_LABELS[0]
    last_lbl = MONTH_LABELS[-1]
    arrow_label = f"{first_lbl} → {last_lbl} 2026"
    # Handle various formatting of month ranges
    html = re.sub(r'Jan[–\- ]+May 2026', period_label, html)
    html = re.sub(r'Jan\s*[–\-→>\u2192]+\s*May\s+2026', arrow_label, html)
    # Handle JS template literal patterns like `Jan \u2192 May` or `Jan → May` (no year)
    html = re.sub(r'Jan\s*[–\-→>\u2192]+\s*May', f'{first_lbl} → {last_lbl}', html)
    html = re.sub(r'JAN\s*[–\-→>\u2192]+\s*MAY', f'{first_lbl.upper()} → {last_lbl.upper()}', html)
    # Replace standalone last-month references
    html = re.sub(r'\bMay 2026\b', f'{last_lbl} 2026', html)
    html = re.sub(r'\bMAY 2026\b', f'{last_lbl.upper()} 2026', html)
    html = re.sub(r"\bMay '26\b", f"{last_lbl} '26", html)
    html = re.sub(r"\bMAY '26\b", f"{last_lbl.upper()} '26", html)
    html = re.sub(r"\bJan '26\b", f"{first_lbl} '26", html)
    html = re.sub(r"\bJAN '26\b", f"{first_lbl.upper()} '26", html)
    # Replace standalone "January" and "May" in non-date contexts (used in some templates)
    html = re.sub(r'\bJanuary\b', first_lbl, html)
    # Rebuild monthLbl object in JS
    month_entries = ", ".join(
        f"2026{m:02d}:'{MONTH_LABELS[i]}'"
        for i, m in enumerate(PERIOD_MONTHS)
    )
    html = re.sub(
        r'const monthLbl = \{.*?\};',
        f'const monthLbl = {{{month_entries}}};',
        html
    )
    return html


def generate_leadership_html(nat_data, template_path, output_path):
    """Generate leadership_summary.html from template."""
    print(f"Generating {output_path.name}...")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace the NAT data block
    html = replace_data_block(html, "NAT", nat_data)

    # Inject dynamic month labels and update hardcoded references
    html = replace_data_block(html, "MONTHS", MONTH_LABELS)
    html = _replace_month_refs(html)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Written to {output_path}")


def generate_zones_html(zones_data, template_path, output_path):
    """Generate zone_scorecards.html from template."""
    print(f"Generating {output_path.name}...")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = replace_data_block(html, "ZONES", zones_data)

    # Inject dynamic month labels and period label
    html = replace_data_block(html, "MONTHS", MONTH_LABELS)
    html = _replace_month_refs(html)

    # Update OA dropdown options to match actual OAs
    oa_names = sorted(zones_data.keys())
    options = "\n".join(f'<option value="{name}">{name}</option>' for name in oa_names)
    html = re.sub(
        r'<select id="oaSelect".*?</select>',
        f'<select id="oaSelect" onchange="renderZone(this.value)">\n{options}\n        </select>',
        html,
        count=1,
        flags=re.DOTALL
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Written to {output_path}")


def generate_fop_html(fop_data, template_path, output_path):
    """Generate fop_dashboard.html from template."""
    print(f"Generating {output_path.name}...")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = replace_data_block(html, "FOP_DATA", fop_data)

    # Inject dynamic month labels
    html = replace_data_block(html, "MONTHS", MONTH_LABELS)
    html = _replace_month_refs(html)

    # Update FOP dropdown options
    fop_names = sorted(fop_data.get("fops", {}).keys())
    options = "\n".join(f'<option value="{name}">{name}</option>' for name in fop_names)
    html = re.sub(
        r'<select id="fopSelect".*?</select>',
        f'<select id="fopSelect" onchange="renderFOP(this.value)">\n{options}\n        </select>',
        html,
        count=1,
        flags=re.DOTALL
    )

    # Update Director dropdown options
    director_names = sorted(fop_data.get("directors", []))
    dir_options = '<option value="">All Directors</option>\n' + "\n".join(
        f'<option value="{name}">{name}</option>' for name in director_names
    )
    html = re.sub(
        r'<select id="directorSelect".*?</select>',
        f'<select id="directorSelect" onchange="renderDirector(this.value)">\n{dir_options}\n        </select>',
        html,
        count=1,
        flags=re.DOTALL
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Written to {output_path}")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("5-Star Report Generator")
    print("=" * 60)

    # Load data
    raw_df = load_data()

    # Filter to analysis period
    df = filter_analysis_data(raw_df)

    # Enrich with Snowflake visit data (FSCC / Brand actual results)
    df = enrich_with_snowflake(df)

    # Assign tiers and binding
    df["_tier"] = df["OVERALL_FIVESTAR"].apply(classify_tier)
    df["_binding"] = df.apply(get_binding, axis=1)

    last_m = PERIOD_MONTHS[-1] if PERIOD_MONTHS else 5
    last_m_label = MONTH_LABELS[-1] if MONTH_LABELS else "May"
    print(f"  Tier distribution ({last_m_label} 2026):")
    may = df[df["MONTHNUM"] == last_m]
    for t in [1, 2, 3]:
        cnt = int((may["_tier"] == t).sum())
        print(f"    {TIER_NAMES[t]}: {cnt}")

    # Load and process workshop data
    workshops_by_oa = load_workshops(df)

    # Compute data products
    nat_data = compute_leadership(df)
    zones_data = compute_zone_scorecards(df, workshops_by_oa)

    # Aggregate national default/at-risk/T1-watch counts from zones_data
    nat_defaulting = sum(z.get("n_defaulting", 0) for z in zones_data.values())
    nat_at_risk = sum(z.get("n_at_risk", 0) for z in zones_data.values())
    nat_t1_watch = sum(z.get("n_t1_watch", 0) for z in zones_data.values())
    nat_data["n_defaulting"] = nat_defaulting
    nat_data["n_at_risk"] = nat_at_risk
    nat_data["n_t1_watch"] = nat_t1_watch

    # Build national watch store list (all DL/AR/TW stores across all zones)
    status_rank = {"dl": 0, "ar": 1, "tw": 2}
    watch_stores = []
    for oa, z in zones_data.items():
        for s in z.get("stores", []):
            if s["st"] in ("dl", "ar", "tw"):
                watch_stores.append({
                    "s": s["s"],
                    "oa": oa,
                    "a": s["a"],
                    "d": s["d"],
                    "f": s["f"],
                    "o": s.get("o", "Unknown"),
                    "st": s["st"],
                    "cu": s["cu"],
                    "sc": s["y"] if s["y"] is not None else s.get(f"m{PERIOD_MONTHS[-1]}" if PERIOD_MONTHS else "m5"),
                    "fscc": s["fscc"],
                    "brand": s["brand"],
                })
    watch_stores.sort(key=lambda x: (status_rank.get(x["st"], 9), x["sc"] if x["sc"] is not None else 99))
    nat_data["watch_stores"] = watch_stores

    # Compute workshop effectiveness and attach to nat_data
    nat_data["workshop_effectiveness"] = compute_workshop_effectiveness(df, workshops_by_oa)

    # Convert to JSON-safe types
    nat_data = convert_for_json(nat_data)
    zones_data = convert_for_json(zones_data)

    # Generate LLM summaries
    summarize_zones(zones_data)
    summarize_leadership(nat_data)

    # Compute FOP dashboard data
    fop_data = compute_fop_data(df, zones_data)
    summarize_fops(fop_data)

    # Attach per-FOP summaries to nat_data for leadership page
    fop_summaries = {}
    for fop_name, fop_info in fop_data.get("fops", {}).items():
        if fop_info.get("summary"):
            fop_summaries[fop_name] = {
                "summary": fop_info["summary"],
                "stores": fop_info.get("n_stores", 0),
                "avg": fop_info.get("avg", None),
                "franchisee": fop_info.get("franchisee", ""),
            }
    nat_data["fop_summaries"] = fop_summaries

    # Attach all workshops (national aggregate) for the Workshops tab
    all_workshops = []
    for oa, odata in workshops_by_oa.items():
        for tk in ("boot_camp", "rising_star"):
            for entry in odata.get(tk, []):
                entry["oa"] = oa
                entry["type_label"] = tk
                all_workshops.append(entry)
    nat_data["all_workshops"] = all_workshops

    # Generate HTML files
    template_dir = BASE_DIR

    generate_leadership_html(
        nat_data,
        template_dir / "leadership_summary.html",
        OUTPUT_DIR / "leadership_summary.html"
    )

    generate_zones_html(
        zones_data,
        template_dir / "zone_scorecards.html",
        OUTPUT_DIR / "zone_scorecards.html"
    )

    generate_fop_html(
        fop_data,
        template_dir / "fop_dashboard.html",
        OUTPUT_DIR / "fop_dashboard.html"
    )

    print("\nAll 3 reports generated successfully!")


if __name__ == "__main__":
    main()
