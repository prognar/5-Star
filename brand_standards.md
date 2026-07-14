# Pizza Hut Brand Standards — 5-Star Operations

## 5-Star Performance Framework

| Component | Code | Description |
|---|---|---|
| Win Score | `WIN_SCORE_STAR` | Guest satisfaction / winning attributes |
| Speed | `SPEED_STAR` | Service speed & delivery times |
| Brand | `BRAND_STAR` | Restaurant brand standards & image |
| Hutbot On-Time | `HB_ONTIME_STAR` | Digital order accuracy & timeliness |
| FSCC | `FSCC_STAR` | Food safety & cleanliness compliance |

### Tier Classification

| Tier | Name | Score Range | Description |
|---|---|---|---|
| 1 | Bootcamp | < 2.5 | Needs immediate improvement |
| 2 | Rising Star | 2.5 – 4.0 | On track, with room to grow |
| 3 | Top Tier | ≥ 4.0 | Excellent performance |

### Weighted Blend (Current)

The overall 5-star score is a weighted average of the five components.
FSCC currently accounts for approximately 7.5% of the blend.

---

## Failure to Satisfy 5-Star Operations Metrics

> *Per the Brand Standards Manual:*

A score **below 2.0 stars** in any fiscal period constitutes a **"Failure to Satisfy 5-Star Operations Metrics."**

- **First failure**: PHLLC may prescribe an initial improvement plan.
- **Second failure within rolling 13 periods**: PHLLC may prescribe an escalated improvement plan.
- **Non-adherence** to a prescribed plan constitutes an additional Failure.

### Default Threshold (Legal)

> *Subject to the Foreword of this Manual, **three consecutive periods** of Failure to Satisfy 5-Star Operations Metrics by a System Restaurant or any **six periods** of Failure to Satisfy 5-Star Operations Metrics by a System Restaurant in a **rolling-13-period timeframe** will constitute a default under the relevant Franchise Agreement(s).*

In operational terms (given our 5-month Jan–May window):
- **Defaulting**: 3+ consecutive months with overall 5-star < 2.0
- **Defaulting (alt.)**: 4+ of the last 5 months with overall 5-star < 2.0

---

## At-Risk (Operational Definition)

A store is **At Risk** when it has posted **2 consecutive months** with an overall 5-star score < 2.0.

At this stage, without intervention from the OPX / FOP team, the store will most likely default. This is the pre-default intervention window.

---

## Tier 1 Watch

A store is in **T1 Watch** when its latest overall score is between **2.0 and 2.5** (Bootcamp tier), it is not already defaulting or at-risk, but it needs attention to prevent slipping into the default zone (< 2.0).

---

## FSCC Component Failures

- FSCC audits occur **2 cycles per year**; every restaurant is audited at least twice per year.
- A failed FSCC audit triggers a retest within **30–60 days**.
- A second consecutive failure constitutes an **escalation notice**.
- **3 consecutive failures** OR **4 of the past 5 failures** = default.

> **Note:** Our automated reports use monthly FSCC_STAR scores as a proxy for audit results. Actual FSCC audit pass/fail data may differ. When B2B and Food Safety check data are ingested, this can be made more precise.

---

## Brand / CORE Component Underperforming

- Brand / CORE visits occur **2 times per year**.
- Same defaulting rules apply: **3 consecutive "Underperforming"** ratings OR **4 of the past 5** = default.

> **Note:** Monthly BRAND_STAR scores are used as a proxy. Actual CORE visit ratings may differ.

---

## Defaulting, At-Risk, and T1 Watch Are FOP-Actionable

These flags identify stores that meet the contractual default thresholds or are approaching them. They are **not directly OA-actionable** — the OA layer uses them for awareness and prioritization. The **Franchise Operations Partner (FOP)** manages the franchisee relationship, improvement plans, and any default proceedings.

---

## Report Integration

The automated 5-Star reports flag these stores as follows:

| Status | Badge | Color | Definition |
|---|---|---|---|
| Defaulting | `DEFAULT` | Red (#a3122a) | ≥3 consecutive months < 2.0★ OR ≥4 of 5 |
| At Risk | `AT RISK` | Amber (#c07f1f) | 2 consecutive months < 2.0★ |
| T1 Watch | `WATCH` | Red outline | Latest score 2.0–2.5★, not DL/AR |

Locations in the reports:
- **Portfolio tab** (zone_scorecards.html): badges on DMA rows, store-level table, and store detail
- **Default Watch** section: replaces the old Focus List — all defaulting/at-risk stores sorted by severity
- **Leadership Summary**: national counts of defaulting, at-risk, and T1 Watch stores (top banner area)
- **FOP Dashboard**: per-FOP AI summaries in the Portfolio Insight box (LLM-generated, 3-paragraph Past | Present | Future for each FOP)
- **Zone Scorecards**: Boot Camp Workshop History section with date-aggregated rows, sparkline trends, and per-store drill-down
- **Leadership Summary**: Workshop Effectiveness section comparing Boot Camp attendees vs. control group
- **Benchmark month**: For workshops, if the workshop date is after the 14th, the benchmark month is the workshop month itself rather than the prior month

---

## FSCC Weighted-Average Gap — Recommendation

**Issue:** The Brand Standards Manual states that any store that fails food safety (FSCC) should be capped at 1-star (Tier 1) for that period. However, the current 5-star formula uses a weighted average of all five components, where FSCC contributes only **~7.5%** of the blend.

**Concrete example:** A store could score **0.0 on FSCC** but still land in **Tier 2 or even Tier 3** if its other four components (Win Score, Speed, Brand, Hutbot) are strong enough to pull the weighted average above 2.5.

**Current reports** match the weighted-average formula exactly — they reflect the data as calculated, not the policy override.

**Recommendation to take up the chain:**

> *Option A — Policy alignment:* Add a post-blend override step: if FSCC_STAR < threshold (e.g. < 2.5), cap OVERALL_FIVESTAR at 1.0 for that period, regardless of other component scores.
>
> *Option B — Policy update:* If the weighted-average formula is intentional, update the Brand Standards Manual to remove or clarify the 1-star cap language so that field expectations match the actual calculation.

---

## Monthly Data Pipeline

The report generator needs up to three input files each month. Most other files (Python script, HTML templates, this document) are static and only change when logic or layout is updated.

### 1. `5-Star.csv` — Monthly, Required

Exported from the 5-Star data source each period after monthly scores close.

| Column | Type | Required | Used For |
|---|---|---|---|
| `CHAINED_STORE_ID` | string | Yes | Store identifier (zero-padded for display) |
| `YEARNO` | number | Yes | Filter to current year |
| `MONTHNUM` | number | Yes | 1–12; Jan–May window currently |
| `STATUSDESC` | string | Yes | Filter `"Open"` only |
| `OVERALL_FIVESTAR` | number | Yes | The blended 5-star score |
| `WIN_SCORE_STAR` | number | Yes | Component — guest satisfaction |
| `SPEED_STAR` | number | Yes | Component — service speed |
| `BRAND_STAR` | number | Yes | Component — brand standards |
| `HB_ONTIME_STAR` | number | Yes | Component — hutbot on-time |
| `FSCC_STAR` | number | Yes | Component — food safety |
| `CURR_FRAN_OWNER_NM` | string | Yes | Franchisee name |
| `NIELSENDMADESC` | string | Yes | DMA designation |
| `OPX_OA` | string | Yes | Zone / OA name (15 values) |
| `OPX_FOP` | string | No | **Franchise Operations Partner** — owner of the franchisee relationship. Required for the FOP Dashboard to function (otherwise all stores show as "Unknown" FOP). |
| `OPX_DIRECTOR` | string | No | **Director** — regional director over multiple FOPs. Adds Director selector to the FOP Dashboard for portfolio roll-up. |
| `FAREADESC` | string | No | Area grouping (if omitted, area drill-down is unavailable; can be populated from Store List) |
| `LATITUDE` | number | No | Map marker latitude (used by Portfolio drill-down) |
| `LONGITUDE` | number | No | Map marker longitude (used by Portfolio drill-down) |
| `SSSG` | number | No | Same-store sales growth (correlation) |
| `SSTG` | number | No | Same-store transaction growth (correlation) |

**Example row:**
```
CHAINED_STORE_ID,YEARNO,MONTHNUM,STATUSDESC,OVERALL_FIVESTAR,WIN_SCORE_STAR,...,OPX_OA,FOP,FAREADESC,LATITUDE,LONGITUDE
"00001",2026,5,Open,3.42,3.1,2.8,3.5,4.2,4.9,"John Smith","DALLAS","Danielle Hudson","Jane FOP","North Dallas",32.87,-96.78
```

**Cadence:** Drop into the `Reporting` folder, replacing the previous month's file. The Python script reads `5-Star.csv` by name.

### 2. `Store List - 7-7-26 v2.csv` — Optional, Reference

Store master with geographic and organizational hierarchy. **Only needed if `FAREADESC`, `LATITUDE`, `LONGITUDE`, or `FOP` are not already in the 5-Star export.** If the file is missing or fails to load, the script proceeds using only 5-Star CSV columns.

| Column | Type | Used For |
|---|---|---|
| `CHAINED_STORE_ID` | string | Join key with 5-Star data |
| `FREGIONDESC` | string | Region grouping |
| `FAREADESC` | string | Area grouping (drill-down level) |
| `LATITUDE` | number | Map markers |
| `LONGITUDE` | number | Map markers |
| `CURR_FRAN_OWNER_NM` | string | Franchisee name override |
| `NIELSENDMADESC` | string | DMA override |
| `FOP` | string | FOP assignment override (or `OPX_FOP` in 5-Star CSV) |
| `DIRECTOR` | string | Director assignment override (or `OPX_DIRECTOR` in 5-Star CSV) |

**Cadence:** Update only when stores open/close or org structure changes.

### 3. `Workshops.csv` — Optional, Boot Camp Data

Boot Camp workshop records. If this file is missing, workshop history and effectiveness sections are hidden.

| Column | Type | Required | Used For |
|---|---|---|---|
| `STORE_NUMBER` | string | Yes | Store identifier (matches `CHAINED_STORE_ID` in 5-Star CSV) |
| `OA_NAME` | string | Yes | OA who ran the workshop |
| `WORKSHOP_DATE` | date (YYYY-MM-DD) | Yes | Workshop date; benchmark month is the workshop month if day > 14, otherwise the prior month |
| `WORKSHOP_TYPE` | string | Yes | Filtered to "Boot Camp" entries |

**Example row:**
```
STORE_NUMBER,OA_NAME,WORKSHOP_DATE,WORKSHOP_TYPE
"00001","Danielle Hudson",2026-03-12,Boot Camp
```

**Benchmark logic:** If the workshop date is after the 14th of the month, the benchmark month is the workshop month itself (the store had already received that month's score before the workshop). If on or before the 14th, the benchmark is the prior month.

### 4. Generated Output Files (do not edit)

| File | Contents |
|---|---|
| `leadership_summary.html` | National executive view with Overview + Default Watch tabs + Workshop Effectiveness (control vs. variable). Per-zone and national LLM summaries. |
| `zone_scorecards.html` | Per-zone drill-down (Overview + Portfolio tabs) with OA LLM summaries + Boot Camp Workshop History (date-aggregated with sparkline trends and per-store drill-down) |
| `fop_dashboard.html` | FOP + Director portfolio view: select Director for FOP roll-up, then FOP → franchisee → store drill-down with detail. Per-FOP LLM summaries in the Portfolio Insight box. |
| `_summaries.json` | Cached LLM summaries (auto-created, do not edit) |

### Monthly Workflow

```
1. Export 5-Star.csv + Workshops.csv  →  drop into Reporting/
2. (Optional) Update Store List if org changed
3. Run:  python generate_reports.py
4. Open fop_dashboard.html, zone_scorecards.html, leadership_summary.html
```

Environment variables needed if using LLM summaries:

```powershell
$env:OPENCODE_SERVER_PASSWORD = "your_password"
```

No other setup required — the script automatically picks up the latest CSV inputs and regenerates all three HTML files.
