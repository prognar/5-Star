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

# ─── Config ────────────────────────────────────────────────────────────────
BASE_DIR = Path("C:/Users/axc1195/OneDrive - Yum! Brands, Inc/Documents/5-Star/Reporting")
FIVESTAR_CSV = BASE_DIR / "5-Star.csv"
STORE_LIST_CSV = BASE_DIR / "Store List - 7-7-26 v2.csv"
OUTPUT_DIR = BASE_DIR

TIER_THRESHOLD = 2.5  # T1 < 2.5, T2 >= 2.5 & < 4.0, T3 >= 4.0
DEFAULT_THRESHOLD = 2.0  # < 2.0 is a "Failure to Satisfy" per brand standards
PERIODS = [202601, 202602, 202603, 202604, 202605]
MONTH_LABELS = {202601: "Jan", 202602: "Feb", 202603: "Mar", 202604: "Apr", 202605: "May"}

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
OPENCODE_SERVER_URL = os.environ.get("OPENCODE_SERVER_URL", "http://127.0.0.1:62464")
OPENCODE_SERVER_USER = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
OPENCODE_SERVER_PASS = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
SUMMARIES_CACHE = BASE_DIR / "_summaries.json"


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

    print("Loading store list...")
    stores = pd.read_csv(
        STORE_LIST_CSV,
        dtype={"CHAINED_STORE_ID": str},
    )
    print(f"  {len(stores):,} stores loaded")

    # Join: bring Area, Lat/Long, DMA, Franchisee from store list
    # Keep all 5-Star rows, left join with store list for enrichment
    join_cols = ["CHAINED_STORE_ID", "CURR_FRAN_OWNER_NM", "NIELSENDMADESC"]
    df = df.merge(
        stores[["CHAINED_STORE_ID", "FREGIONDESC", "FAREADESC", "LATITUDE", "LONGITUDE",
                 "CURR_FRAN_OWNER_NM", "NIELSENDMADESC"]],
        on="CHAINED_STORE_ID",
        how="left",
        suffixes=("", "_sl")
    )
    # Use store list values for fran/dma if available (they're more current)
    # but the CSV already has them, so just use the merged version
    # Fill missing fran/dma from the 5-Star CSV if store list missing
    df["CURR_FRAN_OWNER_NM"] = df["CURR_FRAN_OWNER_NM_sl"].fillna(df["CURR_FRAN_OWNER_NM"])
    df["NIELSENDMADESC"] = df["NIELSENDMADESC_sl"].fillna(df["NIELSENDMADESC"])

    print(f"  Joined: {len(df):,} rows")

    return df


def filter_analysis_data(df):
    """Filter to active stores, Jan-May 2026, with valid 5-Star scores."""
    # Parse YEARNO to get year
    df = df.copy()
    df["_year"] = df["YEARNO"].astype(str).str.extract(r"(\d{4})").astype(float)

    mask = (
        (df["STATUSDESC"] == "Open")
        & (df["_year"] == 2026)
        & (df["MONTHNUM"].isin([1, 2, 3, 4, 5]))
        & (df["OVERALL_FIVESTAR"].notna())
    )
    filtered = df[mask].copy()
    print(f"  Filtered to Jan-May 2026 active with scores: {len(filtered):,} rows")
    return filtered


# ─── Tier Flows ────────────────────────────────────────────────────────────

def compute_tier_flows(monthly_by_store):
    """From store-month data, compute tier transitions from Jan to May."""
    jan = monthly_by_store[monthly_by_store["MONTHNUM"] == 1].copy()
    may = monthly_by_store[monthly_by_store["MONTHNUM"] == 5].copy()

    jan.rename(columns={"OVERALL_FIVESTAR": "score_jan", "_tier": "tier_jan"}, inplace=True)
    may.rename(columns={"OVERALL_FIVESTAR": "score_may", "_tier": "tier_may"}, inplace=True)

    merged = jan[["CHAINED_STORE_ID", "score_jan", "tier_jan"]].merge(
        may[["CHAINED_STORE_ID", "score_may", "tier_may"]],
        on="CHAINED_STORE_ID",
        how="inner"
    )

    start_counts = {1: 0, 2: 0, 3: 0}
    end_counts = {1: 0, 2: 0, 3: 0}
    flows = {f"{f}_{t}": 0 for f in [1, 2, 3] for t in [1, 2, 3]}
    moved_up = 0
    moved_down = 0

    for _, r in merged.iterrows():
        sj, sm = int(r["tier_jan"]), int(r["tier_may"])
        start_counts[sj] = start_counts.get(sj, 0) + 1
        end_counts[sm] = end_counts.get(sm, 0) + 1
        flows[f"{sj}_{sm}"] = flows.get(f"{sj}_{sm}", 0) + 1
        if sm > sj:
            moved_up += 1
        elif sm < sj:
            moved_down += 1

    tier_story = []
    for t in [1, 2, 3]:
        sub = merged[merged["tier_jan"] == t]
        if len(sub) == 0:
            tier_story.append({"t": t, "n": 0, "avgStart": 0, "avgEnd": 0,
                               "stayed": 0, "up": 0, "down": 0})
            continue
        stayed = int((sub["tier_may"] == t).sum())
        up = int((sub["tier_may"] > t).sum()) if t < 3 else 0
        down = int((sub["tier_may"] < t).sum()) if t > 1 else 0
        tier_story.append({
            "t": t,
            "n": len(sub),
            "avgStart": round(float(sub["score_jan"].mean()), 2),
            "avgEnd": round(float(sub["score_may"].mean()), 2),
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

    may_df = df[df["MONTHNUM"] == 5]
    jan_df = df[df["MONTHNUM"] == 1]

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

def compute_zone_scorecards(df):
    """Compute per-OA zone scorecard data."""
    print("Computing zone scorecards...")

    store_df = df  # already has store list info joined

    zones = {}
    for oa in sorted(df["OPX_OA"].dropna().unique()):
        oa_df = df[df["OPX_OA"] == oa]
        z = compute_single_zone(oa_df)
        if z:
            zones[oa] = z

    return zones


def compute_single_zone(zone_df):
    """Compute data for a single OA zone."""
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
        for m in [1, 2, 3, 4, 5]:
            sub = store_months[store_months["MONTHNUM"] == m]
            if len(sub) > 0 and pd.notna(sub["OVERALL_FIVESTAR"].iloc[0]):
                scores[m] = round(float(sub["OVERALL_FIVESTAR"].iloc[0]), 2)

        if len(scores) == 0:
            continue

        q1_vals = [scores[m] for m in [1, 2, 3] if m in scores]
        q2_vals = [scores[m] for m in [4, 5] if m in scores]
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

        # Component scores per month
        comps = {}
        for comp in STAR_COLS:
            vals = []
            for m in [1, 2, 3, 4, 5]:
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
        cons_under = 0
        for m in [5, 4, 3, 2, 1]:
            v = scores.get(m)
            if v is not None and v < DEFAULT_THRESHOLD:
                cons_under += 1
            else:
                break

        total_under = sum(1 for m in [1, 2, 3, 4, 5] if scores.get(m) is not None and scores[m] < DEFAULT_THRESHOLD)

        dl = cons_under >= 3 or total_under >= 4
        ar = cons_under == 2 and not dl
        latest = scores.get(5)
        tw = not dl and not ar and latest is not None and DEFAULT_THRESHOLD <= latest < TIER_THRESHOLD

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

        stores_data.append({
            "s": sid_str,
            "a": str(area),
            "f": str(fran),
            "d": str(dma),
            "m1": scores.get(1),
            "m2": scores.get(2),
            "m3": scores.get(3),
            "m4": scores.get(4),
            "m5": scores.get(5),
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
        })

    # — Default Watch list —
    # Collect: all defaulting → all at-risk → all T1 watch, sorted by severity
    status_rank = {"dl": 0, "ar": 1, "tw": 2, "ok": 3}
    watch_stores = sorted(stores_data, key=lambda s: (status_rank.get(s["st"], 9), s["y"] if s["y"] is not None else 99))
    default_watch = []
    for s in watch_stores[:25]:
        binding = get_binding_for_store(sid=s["s"], zone_df=zone_df)
        default_watch.append({
            "s": s["s"],
            "a": s["a"],
            "f": s["f"],
            "sc": s["y"] if s["y"] is not None else s["m5"],
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

    # Best improvers (Jan -> May delta, only stores in both months)
    jan_may = jan_df[["CHAINED_STORE_ID", "OVERALL_FIVESTAR"]].merge(
        may_df[["CHAINED_STORE_ID", "OVERALL_FIVESTAR"]],
        on="CHAINED_STORE_ID",
        suffixes=("_jan", "_may")
    )
    jan_may["delta"] = jan_may["OVERALL_FIVESTAR_may"] - jan_may["OVERALL_FIVESTAR_jan"]
    best_improvers = jan_may.nlargest(10, "delta")[
        ["CHAINED_STORE_ID", "OVERALL_FIVESTAR_jan", "OVERALL_FIVESTAR_may", "delta"]
    ].to_dict("records")
    for r in best_improvers:
        r["s"] = round(float(r.pop("OVERALL_FIVESTAR_jan")), 2)
        r["e"] = round(float(r.pop("OVERALL_FIVESTAR_may")), 2)
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
    }


# ─── Rising Star Targeting ─────────────────────────────────────────────────

def compute_rising_star(df):
    """Compute DMA x Franchisee targeting data for Tier 2 stores."""
    print("Computing rising star targeting...")

    may_df = df[df["MONTHNUM"] == 5]
    t2 = may_df[may_df["_tier"] == 2].copy()

    print(f"  Tier 2 stores in May: {len(t2)}")

    # DMA x Franchisee groups
    dma_fran = t2.groupby(["NIELSENDMADESC", "CURR_FRAN_OWNER_NM"])

    dma_fran_data = []
    for (dma, fran), grp in dma_fran:
        n_t2 = len(grp)
        # Total stores for this fran in this DMA
        total = len(may_df[(may_df["NIELSENDMADESC"] == dma) & (may_df["CURR_FRAN_OWNER_NM"] == fran)])
        rate = round(n_t2 / total * 100) if total > 0 else 0

        # Primary OA for this group (most stores by that OA)
        oa_counts = grp["OPX_OA"].value_counts()
        primary_oa = oa_counts.index[0]
        n_oa = len(oa_counts)

        # Binding breakdown for Tier 2 stores in this group
        n_bind = len(grp)
        win_pct = round((grp["_binding"] == "WIN_SCORE_STAR").sum() / n_bind * 100) if n_bind > 0 else 0
        speed_pct = round((grp["_binding"] == "SPEED_STAR").sum() / n_bind * 100) if n_bind > 0 else 0
        hb_pct = round((grp["_binding"] == "HB_ONTIME_STAR").sum() / n_bind * 100) if n_bind > 0 else 0
        brand_pct = round((grp["_binding"] == "BRAND_STAR").sum() / n_bind * 100) if n_bind > 0 else 0
        fscc_pct = round((grp["_binding"] == "FSCC_STAR").sum() / n_bind * 100) if n_bind > 0 else 0

        dma_fran_data.append({
            "NIELSENDMADESC": dma if pd.notna(dma) else "Unknown",
            "CURR_FRAN_OWNER_NM": fran if pd.notna(fran) else "Unknown",
            "n_t2": n_t2,
            "oa": primary_oa,
            "n_oa": int(n_oa),
            "win_pct": win_pct,
            "speed_pct": speed_pct,
            "hb_pct": hb_pct,
            "brand_pct": brand_pct,
            "fscc_pct": fscc_pct,
            "total": total,
            "rate": rate,
        })

    dma_fran_data.sort(key=lambda x: x["n_t2"], reverse=True)
    top30 = dma_fran_data[:30]

    # Map points
    binding_code_map = {
        "WIN_SCORE_STAR": "W", "SPEED_STAR": "S",
        "BRAND_STAR": "B", "HB_ONTIME_STAR": "H", "FSCC_STAR": "F"
    }

    points = []
    for _, r in t2.iterrows():
        lat = r.get("LATITUDE")
        lon = r.get("LONGITUDE")
        if pd.isna(lat) or pd.isna(lon):
            continue
        binding_code = binding_code_map.get(r["_binding"], "W")
        points.append({
            "lat": round(float(lat), 3),
            "lon": round(float(lon), 3),
            "dma": str(r["NIELSENDMADESC"]) if pd.notna(r["NIELSENDMADESC"]) else "Unknown",
            "fran": str(r["CURR_FRAN_OWNER_NM"]) if pd.notna(r["CURR_FRAN_OWNER_NM"]) else "Unknown",
            "oa": str(r["OPX_OA"]) if pd.notna(r["OPX_OA"]) else "Unknown",
            "binding": binding_code,
            "score": round(float(r["OVERALL_FIVESTAR"]), 2),
            "store": int(float(r["CHAINED_STORE_ID"])),
        })

    return {
        "dmaFranData": top30,
        "points": points,
        "n_t2_total": len(t2),
    }


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
        with urllib.request.urlopen(req, timeout=10) as resp:
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
        with urllib.request.urlopen(req2, timeout=180) as resp:
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


def summarize_zones(zones_data):
    """Generate LLM summaries for each OA zone using the opencode server."""
    oa_names = sorted(zones_data.keys())

    # Check cache
    cache = {}
    if SUMMARIES_CACHE.exists():
        try:
            with open(SUMMARIES_CACHE, "r") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            cache = {}

    # Check if all OAs have cached summaries
    if all(oa in cache for oa in oa_names):
        print("  Using cached LLM summaries")
        for oa in oa_names:
            zones_data[oa]["summary"] = cache[oa]
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

        oa_data[oa] = {
            "stores": z["n_stores"],
            "fran": z["n_fran"],
            "avg_may": z["headline_avg"],
            "avg_jan": z["base_avg"],
            "tier_start": z["startCounts"],
            "tier_end": z["endCounts"],
            "up": z["moved_up"],
            "down": z["moved_down"],
            "bind_t1": {k: v for k, v in top_bind_t1},
            "bind_t2": {k: v for k, v in top_bind_t2},
            "t1_hotspots": [
                {"a": a["FAREADESC"], "n": a["n_t1"], "r": a["rate"]}
                for a in bootcamp[:3]
            ],
            "low_areas": [
                {"a": a["FAREADESC"], "avg": a["avg"]} for a in low_areas[:3]
            ],
            "high_areas": [
                {"a": a["FAREADESC"], "avg": a["avg"]} for a in high_areas[:3]
            ],
            "top_improvers": [
                {"s": i["CHAINED_STORE_ID"], "d": i["delta"]}
                for i in improvers[:3]
            ],
        }

    system_prompt = (
        "You are a 5-Star operations analyst for a major pizza chain. "
        "Write concise, actionable 1-2 paragraph summaries for each OA zone. "
        "Focus on: what's working, what's at risk, the biggest binding constraint "
        "holding the zone back, and the single most important action the OA should take. "
        "Use specific numbers. Be direct and operational — this is for OAs who know "
        "their business and need insight, not fluff."
    )

    user_prompt = (
        "Here is the Jan-May 2026 5-Star data for all 15 OAs:\n\n"
        + json.dumps(oa_data, indent=2)
        + "\n\nReturn a JSON object with a 'summaries' key mapping each OA name "
        "to a 1-2 paragraph summary."
    )

    result = call_opencode_server([user_prompt], system_prompt=system_prompt)
    if result is None:
        print("  LLM call failed, proceeding without summaries")
        return

    summaries = result.get("summaries", {})
    for oa in oa_names:
        summary = summaries.get(oa, "")
        if summary:
            zones_data[oa]["summary"] = summary
            cache[oa] = summary

    # Write cache
    try:
        with open(SUMMARIES_CACHE, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"  Cached {len(summaries)} summaries to {SUMMARIES_CACHE.name}")
    except IOError as e:
        print(f"  Could not write cache: {e}")


# ─── HTML Rendering ────────────────────────────────────────────────────────

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


def generate_leadership_html(nat_data, template_path, output_path):
    """Generate leadership_summary.html from template."""
    print(f"Generating {output_path.name}...")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace the NAT data block
    html = replace_data_block(html, "NAT", nat_data)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Written to {output_path}")


def generate_rising_star_html(rising_data, template_path, output_path):
    """Generate rising_star.html from template."""
    print(f"Generating {output_path.name}...")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = replace_data_block(html, "dmaFranData", rising_data["dmaFranData"])
    html = replace_data_block(html, "points", rising_data["points"])

    # Update the headline number for Tier 2 count
    html = re.sub(
        r'(<div class="num">)\d+([,.]?\d*)(</div>\s*<div class="lbl">Tier 2)',
        rf'\g<1>{rising_data["n_t2_total"]}\g<3>',
        html
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Written to {output_path}")


def generate_zones_html(zones_data, template_path, output_path):
    """Generate zone_scorecards.html from template."""
    print(f"Generating {output_path.name}...")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = replace_data_block(html, "ZONES", zones_data)

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


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("5-Star Report Generator")
    print("=" * 60)

    # Load data
    raw_df = load_data()

    # Filter to analysis period
    df = filter_analysis_data(raw_df)

    # Assign tiers and binding
    df["_tier"] = df["OVERALL_FIVESTAR"].apply(classify_tier)
    df["_binding"] = df.apply(get_binding, axis=1)

    print(f"  Tier distribution (May 2026):")
    may = df[df["MONTHNUM"] == 5]
    for t in [1, 2, 3]:
        cnt = int((may["_tier"] == t).sum())
        print(f"    {TIER_NAMES[t]}: {cnt}")

    # Compute data products
    nat_data = compute_leadership(df)
    zones_data = compute_zone_scorecards(df)
    rising_data = compute_rising_star(df)

    # Aggregate national default/at-risk/T1-watch counts from zones_data
    nat_defaulting = sum(z.get("n_defaulting", 0) for z in zones_data.values())
    nat_at_risk = sum(z.get("n_at_risk", 0) for z in zones_data.values())
    nat_t1_watch = sum(z.get("n_t1_watch", 0) for z in zones_data.values())
    nat_data["n_defaulting"] = nat_defaulting
    nat_data["n_at_risk"] = nat_at_risk
    nat_data["n_t1_watch"] = nat_t1_watch

    # Convert to JSON-safe types
    nat_data = convert_for_json(nat_data)
    zones_data = convert_for_json(zones_data)
    rising_data = convert_for_json(rising_data)

    # Generate LLM summaries for each OA
    summarize_zones(zones_data)

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

    generate_rising_star_html(
        rising_data,
        template_dir / "rising_star.html",
        OUTPUT_DIR / "rising_star.html"
    )

    print("\nAll reports generated successfully!")


if __name__ == "__main__":
    main()
