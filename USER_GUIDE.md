# 5-Star Reports — Quick Start Guide

Four HTML dashboards, generated from `5-Star.csv` and optional `Workshops.csv`. Open in any browser.

---

## Operating the Scorecard

### Requirements

- **Python 3.9+** with standard library (no pip packages required)
- **(Optional) OpenCode LLM server** — set `OPENCODE_SERVER_PASSWORD` to enable AI-generated narrative summaries. Without it, data-driven fallback summaries are used and reports always have content.
- **Monthly CSV** — the script auto-detects which months are present in the CSV and adjusts all labels, sparklines, and scoring windows accordingly. No month references are hardcoded.

### Required Files

Drop these into the `Reporting` folder:

| File | Description |
|---|---|
| `5-Star.csv` | Monthly 5-Star store scores with FOP, Director, DMA, Franchisee, and component breakdowns |

### Optional Files

| File | Description |
|---|---|
| `Workshops.csv` | Boot Camp and Rising Star workshop attendance records — enables the Workshops tab and workshop effectiveness analysis |

### Running the Script

```powershell
python generate_reports.py
```

Outputs four self-contained HTML files. No server, no database — share them as file attachments.

### LLM Summaries

Summaries are cached in `_summaries.json`. Delete this file to force regeneration. If the OpenCode server is unavailable, deterministic fallback summaries (data-driven) are used for leadership, zones, and FOPs — the reports always have content.

### Exporting Data from Snowflake

Run these queries and save the results as CSVs in the `Reporting` folder.

<details>
<summary><code>5-Star.csv</code> — store-month scores</summary>

```sql
SELECT
    CHAINED_STORE_ID
    ,YEARNO
    ,MONTHNUM
    ,STATUSDESC
    ,NIELSENDMADESC AS DMA
    ,CURR_FRAN_OWNER_NM AS FRANCHISEE
    ,FREGIONDESC AS REGION_COACH
    ,FAREADESC AS AREA_COACH
    ,CONCEPTDESC AS CONCEPT
    ,LATITUDE
    ,LONGITUDE
    ,OPX_OA AS OA
    ,OPX_FOP AS FOP
    ,OPX_DIRECTOR AS DIRECTOR
    ,CY_SS_SALES_TNS AS SALES
    ,LY_SS_SALES_TNS AS SALES_LY
    ,DIV0(CY_SS_SALES_TNS,LY_SS_SALES_TNS) AS SSSG
    ,CY_SS_TRANS AS TRANSACTIONS
    ,LY_SS_TRANS AS TRANSACTIONS_LY
    ,DIV0(CY_SS_TRANS,LY_SS_TRANS) AS SSTG
    ,OVERALL_FIVESTAR AS FIVESTAR
    ,SPEED_ACTUAL
    ,SPEED_STAR
    ,WIN_SCORE_ACTUAL
    ,WIN_SCORE_STAR
    ,BRAND_ACTUAL
    ,BRAND_STAR
    ,HB_ONTIME_ACTUAL AS HUTBOT_ACTUAL
    ,HB_ONTIME_STAR AS HUTBOT_STAR
    ,FSCC_ACTUAL
    ,FSCC_STAR
FROM AXC1195.FXT_DASHBOARD_BASE_MONTHLY
WHERE YEARNO = '2026'
  AND CURR_FRAN_OWNER_NM <> 'PIZZA HUT OF AMERICA, LLC. (PHI01-060010)'
ORDER BY CHAINED_STORE_ID, YEARNO, MONTHNUM;
```

</details>

<details>
<summary><code>Workshops.csv</code> — workshop attendance</summary>

```sql
SELECT
    WR.STORE_NUMBER,
    W.WORKSHOP_ID,
    W.WORKSHOP_DATE,
    W.WORKSHOP_TYPE,
    W.OA_NAME
FROM AXC1195.WORKSHOP W
INNER JOIN AXC1195.WORKSHOP_RESTAURANT WR
    ON W.WORKSHOP_ID = WR.WORKSHOP_ID
ORDER BY W.WORKSHOP_DATE, WR.STORE_NUMBER;
```

</details>

---

## 1. `leadership_summary.html` — National Executive View

**Audience:** Leadership, Directors, Strategy.

**What it does:** National roll-up of all zones in one page. Overview + Default Watch + Workshops tabs.

### Overview tab
- **National Insight** (above tabs) — a flowing narrative summary: what happened, current state, top priority. LLM-generated when server is available; otherwise data-driven fallback.
- **Zone Ranking** — all zones sorted by current average with gradient trend indicators (green = improving, red = declining, darker = more severe)
- **Tier Movement (Sankey)** — how stores flowed between tiers over the period
- **National Trend (chart)** — 5-month line chart of overall average and each component
- **Binding chart** — for each tier nationally, which component is the lowest score. Each store's "binding constraint" is its worst-scoring component (Win Score, Speed, Brand, Hutbot, or FSCC). The chart shows what percentage of stores in each tier are held back by each component. If 54% of Tier 1 stores are bound on Speed, that's where to focus coaching — not Brand, not Win Score.
- **FOP Summaries** — per-FOP 3-paragraph summaries (Past | Present | Future) showing portfolio shifts, risk distribution, and recommended actions

### Default Watch tab
- Every defaulting, at-risk, and T1-watch store nationwide sorted by severity with OA, Franchisee, DMA, and consecutive months

### Workshops tab
- **Workshop Effectiveness** — control vs. variable comparison for Boot Camp **and** Rising Star. Control group = stores in the same tier (T1 for bootcamp, T2 for rising star) at the baseline month that did not attend a workshop of that type. Compares whether attending stores improved more than their tier peers who didn't attend. Validates the program investment.
- **Date-Aggregated Workshop List** — all workshops across all zones, grouped by date and facilitator. Filter by type (All / Boot Camp / Rising Star) via toggle buttons, or by franchisee via dropdown. Each date card has a colored left border — blue for BC-only, purple for RS-only. Each store row shows a BC/RS type tag, post-workshop scores with improvement deltas, and sparkline trend. Same-day workshops by different Area Coaches appear as separate blocks.
- **Franchisee Filter** — filter workshops by franchisee to isolate stores within a specific ownership group
- **Area Coach Grouping** — same-day workshops are grouped by Area Coach (`FAREADESC`), showing distinct blocks when multiple Area Coaches host on the same date
- **Per-FOP Summaries** — same FOP summaries from the Overview tab, surfaced here for context

---

## 2. `fz_dashboard.html` — Franchisee Dashboard

**Audience:** FOPs (Franchise Operations Partners) and Directors.

**What it does:** Portfolio view of all franchisees, segmented by Director → FOP. Defaults to the full cross-portfolio view so you see every franchisee and which FOP/Director manages them.

### Navigation

| Step | What you see |
|---|---|
| **Default (All Directors + All FOPs)** | Full portfolio of every franchisee with FOP & Director columns, sorted by defaulting count. Headline score = national weighted average across all stores |
| Select a **Director** | Aggregate stats for that director's territory + their franchisees (grouped by FOP). Headline score updates to that director's store-weighted average |
| Select a **FOP** (or click a franchisee row) | AI summary (3-paragraph Past \| Present \| Future) + franchisee table for that FOP. Headline score updates to that FOP's average |
| Click a **franchisee** row | Store list with status badges, scores, trend arrows, search, and Region/Area Coach filter dropdowns. Headline score updates to that franchisee's average |
| Click **Detail** on a store | Full component breakdown with monthly scores, sparklines, and status banner. Back button returns to the franchisee store list |

### Score Mode Toggle

Toggle between **LM** (Last Month), **LQ** (Last Quarter), and **YTD** (Year-to-Date) to change how scores are displayed. The headline score and all table averages update to reflect the selected mode. In LQ mode, scores are computed as a rolling 3-month average.

### Trend Arrows

Trend arrows use gradient coloring to indicate severity:
- **Green** (↑) — improving. Darker green = stronger improvement
- **Red** (↓) — declining. Darker red = steeper decline
- **Gray** (→) — flat / no meaningful change

Severity thresholds: >0.3 slope = strong, >0.15 = moderate, else mild.

### Status Framework

Status is recomputed from store data at render time (not from the CSV) using the following logic:

| Status | Criteria | Action |
|---|---|---|
| **Defaulting (dl)** | 3+ consecutive months < 2.0★ | FOP escalates, OA builds plan |
| **At Risk (ar)** | 2 consecutive months < 2.0★ | Preventative intervention needed |
| **T1 Watch (tw)** | Latest score 2.0–2.5★ | Monitor, address before it worsens |
| **OK** | Everything else | Business as usual |

---

## 3. `zone_scorecards.html` — OA Zone Scorecard

**Audience:** OAs (Operations Assistants / Zone Managers).

**What it does:** Per-zone deep dive. Select a zone from the dropdown. Four tabs. Headline score updates to the selected zone's weighted average.

### Overview tab
- **Goal Tracker** — T1 reduction, T3 growth, and gross stores moved up (target: 75, not net). Progress bar shows pace toward the annual goal.
- **Tier Cards** — "Right now" snapshot for each tier: current store count with directional change from January, current average score (2 decimal places) vs January, and where stores moved. Header shows "N stores now". Verdict sentence summarizes the story in one read.
- **Sankey** — zone-level tier flow diagram
- **Trend chart** — line chart with component overlays (x-axis labels adapt to available months)
- **Binding chart** — per-tier breakdown of what's holding stores back. Each store's worst component (Win Score, Speed, Brand, Hutbot, or FSCC) is its binding constraint. The stacked bar shows what % of stores in each tier are bound by each component — tells the OA where to focus coaching.
- **Area & Franchisee Spotlight** — lowest/highest areas and best/worst franchisee
- **Default Watch** — zone's defaulting/at-risk/T1-watch stores

### Portfolio tab (OA Portfolio Drill-Down)
- Drill-down: **OA → DMA → Area → Store → Component**
- Toggle between Monthly/Quarterly/YTD view
- Click **Detail** on a store for component breakdown with sparklines
- Trend arrows use gradient coloring (green improving, red declining, darker = more severe)

### Boot Camps tab
- **Past Workshops** — completed workshops grouped by date. Each date row shows store count, Area Coach(s), average baseline score, monthly post-scores with sparkline trend, and net delta. Click to drill down to per-store Pre Score / Post Scores / Delta detail.
- **Future Workshops** — upcoming workshops showing store count, Area Coach(s), and average baseline score only. No post-scores or trend — the store hasn't attended yet.
- **Baseline logic** — the baseline is a rolling 3-month average of the latest available 5-star data before the workshop. Follow-ups use fixed periods: 30-day (next month only), 60-day (next 2 months averaged), 90-day (next 3 months averaged). Each store serves as its own baseline — the baseline score is the average of months (workshop_month-3, workshop_month-2, workshop_month-1), pre-score is the score 5 months before the baseline end, and post-scores are the follow-up period averages. Only computed when the required months exist in available data and the workshop date is in the past. Future workshops show no baseline or post-scores — the store hasn't attended yet.
- **Status classification** — workshop is "past" if the date is before today, "future" otherwise (regardless of whether the month's data has landed yet)

### Targeting tab
- **Bootcamp Targeting Table** — Tier 1 stores ranked by area with DMA, franchisee, concentration, and binding focus bars

---

## 4. `rising_star.html` — Rising Star Targeting

**Audience:** OAs, Directors, Leadership (cross-zone targeting).

**What it does:** A zone-agnostic view of all Tier 2 (Rising Star) stores nationally, to target development workshops at DMA×Franchisee hot spots.

### Sections
- **Map** — every Tier 2 store plotted, colored by binding constraint. Click a legend item to filter to that binding only; click again to show all. Unselected items dim to 35% opacity.
- **Top 30 DMA×Franchisee Targets** — sorted by Tier 2 count, with concentration rate, OA(s), and binding focus bars
- **Rising Star Workshop History** — past and upcoming workshops with per-store pre/post scores and delta

**Why zone-agnostic:** Rising Star targeting cuts across OA zone boundaries — it follows franchisee footprint within a DMA, so a row may span multiple OAs.

---
