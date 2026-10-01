# 5-Star Reports — Quick Start Guide

Four HTML dashboards, generated from `5-Star.csv` and optional `Workshops.csv`. Open in any browser.

---

## Operating the Scorecard

### Requirements

- **Python 3.9+**, plus the `anthropic` package (`pip install anthropic`) if you want AI-generated summaries
- **(Optional) Claude API access** — set `ANTHROPIC_API_KEY` (or run `ant auth login`) to enable AI-generated narrative summaries. Without it, data-driven fallback summaries are used and reports always have content.
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
| `Alignment.csv` | Store org-hierarchy alignment (OA, Zone, FOP, Director, DMA, Region, Area, address, lat/long, rolling 3-month 5-Star avg, Tier) — enables the Alignment tab on the Franchisee Dashboard |

### Running the Script

```powershell
python generate_reports.py
```

Outputs four self-contained HTML files. No server, no database — share them as file attachments.

### LLM Summaries

Summaries are cached in `_summaries.json`. Delete this file to force regeneration — the cache does not invalidate on its own when only the summary-generation logic changes, only when the report's month range changes. If the Claude API is unavailable (no `ANTHROPIC_API_KEY` / auth profile, or a request fails), deterministic fallback summaries (data-driven) are used for leadership, zones, and FOPs — the reports always have content.

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

<details>
<summary><code>Alignment.csv</code> — store org-hierarchy alignment (optional; powers the Alignment tab in <code>fz_dashboard.html</code>)</summary>

Run `USE DATABASE DATASCIENCE;` first (the connection has no default database).

```sql
WITH MONTH_LOOKUP AS (
    SELECT * FROM VALUES
        ('JANUARY',1),('FEBRUARY',2),('MARCH',3),('APRIL',4),
        ('MAY',5),('JUNE',6),('JULY',7),('AUGUST',8),
        ('SEPTEMBER',9),('OCTOBER',10),('NOVEMBER',11),('DECEMBER',12)
    AS T(MONTHNAME, MONTHNO)
),
FIVESTAR_MONTHLY AS (
    SELECT DISTINCT
         V.CHAINED_STORE_ID
        ,V.YEARNO
        ,V.MONTHNAME
        ,V.OVERALL_FIVESTAR
        ,CAST(REPLACE(V.YEARNO, 'Y', '') AS INT) * 12 + ML.MONTHNO AS MONTH_SEQ
    FROM AXC1195.VW_FIVESTAR_SUMMARY V
    JOIN MONTH_LOOKUP ML ON V.MONTHNAME = ML.MONTHNAME
),
LATEST_SEQ AS (
    SELECT CHAINED_STORE_ID, MAX(MONTH_SEQ) AS LATEST_MONTH_SEQ
    FROM FIVESTAR_MONTHLY
    WHERE OVERALL_FIVESTAR IS NOT NULL
    GROUP BY ALL
),
FIVESTAR_3MO AS (
    SELECT F.CHAINED_STORE_ID, ROUND(AVG(F.OVERALL_FIVESTAR), 2) AS FIVESTAR_AVG_3MO
    FROM FIVESTAR_MONTHLY F
    JOIN LATEST_SEQ L ON F.CHAINED_STORE_ID = L.CHAINED_STORE_ID
       AND F.MONTH_SEQ BETWEEN L.LATEST_MONTH_SEQ - 2 AND L.LATEST_MONTH_SEQ
    WHERE F.OVERALL_FIVESTAR IS NOT NULL
    GROUP BY ALL
)
ZONE_LATEST AS (
    -- Zone comes from whichever of MANUAL_ZONE_OVERRIDES / STORE_ZONE_MAP was
    -- updated most recently for that store — NOT from OPX_ALIGNMENT, which
    -- can disagree with these two (confirmed 364 stores in disagreement as of
    -- 2026-09-30) and is missing ~119 open stores entirely.
    SELECT CHAINED_STORE_ID, ZONE
    FROM (
        SELECT CHAINED_STORE_ID, ZONE, UPDATED_TS,
            ROW_NUMBER() OVER (PARTITION BY CHAINED_STORE_ID ORDER BY UPDATED_TS DESC) AS RN
        FROM (
            SELECT CHAINED_STORE_ID, ZONE, UPDATED_TS FROM AXC1195.MANUAL_ZONE_OVERRIDES
            UNION ALL
            SELECT CHAINED_STORE_ID, ZONE, UPDATED_TS FROM AXC1195.STORE_ZONE_MAP
        )
    )
    WHERE RN = 1
),
FOP_LATEST AS (
    -- FOP is assigned per-FRANCHISEE (not per-store) via OPX_FRAN_FOP_MAP.
    SELECT FRANCHISEE_NAME, FOP_NAME
    FROM (
        SELECT FRANCHISEE_NAME, FOP_NAME, UPDATED_TS,
            ROW_NUMBER() OVER (PARTITION BY FRANCHISEE_NAME ORDER BY UPDATED_TS DESC) AS RN
        FROM AXC1195.OPX_FRAN_FOP_MAP
        WHERE IS_ACTIVE = 1
    )
    WHERE RN = 1
),
DIRECTOR_LATEST AS (
    -- Director is assigned per-FOP via OPX_FOP_DIRECTOR_MAP.
    SELECT FOP_NAME, DIRECTOR_NAME
    FROM (
        SELECT FOP_NAME, DIRECTOR_NAME, UPDATED_TS,
            ROW_NUMBER() OVER (PARTITION BY FOP_NAME ORDER BY UPDATED_TS DESC) AS RN
        FROM AXC1195.OPX_FOP_DIRECTOR_MAP
        WHERE IS_ACTIVE = 1
    )
    WHERE RN = 1
)
SELECT
     A.CHAINED_STORE_ID
    ,A.CURR_FRAN_OWNER_NM AS FRANCHISEE
    ,O.OA
    ,Z.ZONE
    ,FM.FOP_NAME
    ,DM.DIRECTOR_NAME
    ,A.NIELSENDMADESC AS DMA
    ,A.FREGIONDESC AS REGION
    ,A.FAREADESC AS AREA
    ,A.RESTMAILADDR1
    ,A.RESTMAILCITYNM AS CITY
    ,A.RESTMAILSTATEID AS STATE
    ,A.LATITUDE
    ,A.LONGITUDE
    ,FS.FIVESTAR_AVG_3MO
    ,CASE
        WHEN FS.FIVESTAR_AVG_3MO >= 4   THEN 'Tier 3'
        WHEN FS.FIVESTAR_AVG_3MO >= 2.5 THEN 'Tier 2'
        WHEN FS.FIVESTAR_AVG_3MO IS NOT NULL THEN 'Tier 1'
        ELSE NULL
     END AS TIER
FROM DSC.ALIGN_DIM_V1 A
LEFT JOIN FIVESTAR_3MO FS ON A.CHAINED_STORE_ID = FS.CHAINED_STORE_ID
LEFT JOIN ZONE_LATEST Z ON A.CHAINED_STORE_ID = Z.CHAINED_STORE_ID
LEFT JOIN AXC1195.ZONE_OA_MAP O ON Z.ZONE = O.ZONE
-- OA is derived FROM the zone (ZONE_OA_MAP is a clean 15-row 1:1 lookup), not
-- stored per-store — this is why OA never needs its own override table.
LEFT JOIN FOP_LATEST FM ON UPPER(A.CURR_FRAN_OWNER_NM) = UPPER(FM.FRANCHISEE_NAME)
LEFT JOIN DIRECTOR_LATEST DM ON FM.FOP_NAME = DM.FOP_NAME
WHERE A.OWNERID <> 'L'
  AND A.CURR_FRAN_OWNER_NM NOT LIKE 'PIZZA HUT%'
  AND A.STATUSDESC = 'Open';
```

**Why not join `OPX_ALIGNMENT` directly (the first version of this query)?** It was missing ~119 open stores entirely and disagreed with `STORE_ZONE_MAP` on Zone for 364 more — confirmed by querying both tables directly. The corrected query above (the production pattern already used elsewhere) brought unmapped stores from 119 down to 0. If a store still comes back unmapped, add it to `AXC1195.MANUAL_ZONE_OVERRIDES` directly in Snowflake — the SQL already reads from that table, so no code change is needed here.

No LLM/Claude call is involved in this pipeline — it's a pure Snowflake query → CSV → static HTML table.

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
- **Workshop Summary** — key metrics at a glance: workshops held, upcoming, stores improved, stores not improved — broken out by Boot Camp (red) and Rising Star (gold)
- **Workshop Effectiveness** — control vs. variable comparison for Boot Camp **and** Rising Star. Control group = stores in the same tier (T1 for bootcamp, T2 for rising star) at the baseline month that did not attend a workshop of that type. Compares whether attending stores improved more than their tier peers who didn't attend. Validates the program investment.
- **Date-Aggregated Workshop List** — all workshops across all zones, grouped by date and facilitator. Filter by type (All / Boot Camp / Rising Star) via toggle buttons, or by franchisee via dropdown. Each date card has a colored left border — red for BC, gold for RS. Each store row shows post-workshop scores with improvement deltas, and sparkline trend. Same-day workshops by different Area Coaches appear as separate blocks.
- **Export CSV** — export all workshop data (filtered by type) with DATE, WORKSHOP_TYPE, AREA_COACH, STORE, BASELINE, 30d, 60d, 90d, CHANGE (latest check-in minus baseline)
- **Franchisee Filter** — filter workshops by franchisee to isolate stores within a specific ownership group
- **Area Coach Grouping** — same-day workshops are grouped by Area Coach (`FAREADESC`), showing distinct blocks when multiple Coaches host on the same date
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

Toggle between **LM** (Last Month), **LQ** (Last Quarter), and **YTD** (Year-to-Date) to change how scores are displayed. The toggle is **unified** — it drives the headline score, the metric cards, the quintile window, and every table average together. In LQ mode, scores are computed as a rolling 3-month average (last 3 months, e.g. Jun–Aug). The default mode is YTD. The quintile section stays visible at every drill level, including franchisee — at the franchisee level it shows the parent FOP's quintile breakdown as top-of-page context while the store list below is franchisee-specific.

### Alignment Tab

A second tab (**Portfolio** / **Alignment**) alongside the drill-down view above. Lists every open franchised store from `Alignment.csv` (org-hierarchy: OA, Zone, FOP, Director, DMA, Region, Area, mailing address, lat/long, rolling 3-month 5-Star average, and Tier) in one flat, sortable, filterable table — independent of the Portfolio tab's Director/FOP drill-down.

- **Sort:** click any column header to sort ascending/descending (same `.sortable` pattern as the rest of the app).
- **Filter:** dropdowns for Zone, FOP, Director, State, and Tier (all low-cardinality, built from the data at render time) plus a free-text search box that matches store #, franchisee, city, DMA, area, and region — covers the higher-cardinality fields (Area has ~700 distinct values, DMA ~200, Region ~190) without needing 700-option dropdowns.
- **Export CSV:** exports exactly the currently filtered + sorted rows (not the full table) — what's on screen is what you get. The downloaded filename encodes the active filters (e.g. `Store_Alignment_zone-DeepSouth_tier-Tier1_2026-09-29.csv`) so a shared export is self-documenting about what it contains.
- No LLM/Claude call is involved anywhere in this tab.

**Every open store should have a Zone/OA.** `Alignment.csv` only includes open stores (`STATUSDESC = 'Open'` in the SQL), so any store still showing "Unassigned" is a genuine gap, not a closed-store artifact. The SQL (see below) already resolves Zone from `AXC1195.MANUAL_ZONE_OVERRIDES` ∪ `STORE_ZONE_MAP` (most-recently-updated wins) and derives OA from Zone via `AXC1195.ZONE_OA_MAP`, so this should normally be empty. If `generate_reports.py` ever finds a gap anyway, it writes the current list to `Unmapped_Zone_Stores.csv` (store #, franchisee, DMA, city, state, lat/long) — the fix for any store on that list is to add it to `AXC1195.MANUAL_ZONE_OVERRIDES` in Snowflake directly (the real override table the SQL reads from), not to the report generator's code.

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
- **Baseline logic** — the baseline is an average of available 5-star data before the workshop. The anchor month depends on the workshop day: on/after the 15th → anchor = workshop_month - 1; before the 15th → anchor = workshop_month - 2. Baseline = average of available months from (anchor-2, anchor-1, anchor) — uses whatever data exists (1, 2, or 3 months). Follow-ups start the month after the workshop: 30-day (month 1 after), 60-day (average of months 1–2 after), 90-day (average of months 1–3 after) — also uses available months. Export includes CHANGE column (latest check-in minus baseline).
- **Status classification** — workshop is "past" if the date is before today, "future" otherwise (regardless of whether the month's data has landed yet)

### Targeting tab
- **Bootcamp Targeting Table** — Tier 1 stores ranked by area with DMA, franchisee, concentration, and binding focus bars

---

## 4. `rising_star.html` — Rising Star Targeting

**Audience:** OAs, Directors, Leadership (cross-zone targeting).

**What it does:** A zone-agnostic view of all Tier 2 (Rising Star) stores nationally, to target development workshops at DMA×Franchisee hot spots.

### Sections
- **Map** — every Tier 2 store plotted, colored by binding constraint. Click a legend item to filter to that binding only; click again to show all. Unselected items dim to 35% opacity.
- **All DMA×Franchisee Targets** — every DMA×Franchisee combination with Tier 2 stores, sorted by count with concentration rate, OA(s), binding focus bars, and workshop status badge (Completed/Scheduled/None)
- **Rising Star Workshops** — date-grouped cards matching Leadership Summary format (gold background), expandable to Area Coach cards with store count, then drill to individual stores with baseline, 30/60/90 post scores, sparkline trend, and deltas

**Why zone-agnostic:** Rising Star targeting cuts across OA zone boundaries — it follows franchisee footprint within a DMA, so a row may span multiple OAs.

---

## 5. `leadership_brief.html` — Leadership Brief (Private)

**Audience:** Leadership only (recognition-focused). **Not linked** from the shared pages — open the file directly.

**What it does:** A single, LLM-driven executive pulse that pulls together national highlights, OA recognition, Boot Camp performance, and franchisee movement into one page refreshed each month when 5-Star and workshop data update.

### Sections
- **National Summary** — LLM narrative covering *What's working well* and *Where the opportunities are*, backed by the period's numbers.
- **Recognition Spotlight** — 1–2 named OAs who "swung hard" this period (the standout can change month to month). The LLM picks whoever has the strongest data-backed story — biggest average move, Tier 1 reduction / stores moved up, or Boot Camp impact.
- **OA Front** — zone grid: stores, from→to average, Δ avg, T1/T3 movement, and workshops held/upcoming.
- **Boot Camp Pulse** — KPI cards (held / upcoming / stores improved / lift vs control), an LLM narrative covering 30/60/90 follow-ups, number completed this period, how effective they've been, and who did the most, plus a per-zone effectiveness table.
- **Franchisee Level** — franchisees on the rise (largest LQ→latest improvement) and franchisees to watch (by defaulting/at-risk/watch counts).

### Data refresh
Runs automatically as part of `python generate_reports.py`. The three LLM narratives are cached in `_summaries.json` under `_brief_version`; they regenerate when the month range changes. If the Claude API is unavailable, the data-driven tables and cards still render (narrative spots show a placeholder and reuse the last good cached text when available).

---
---

## Reporting session changelog — 2026-09-30

All changes below are **durable**: they live in `generate_reports.py`. Verified after `python generate_reports.py --run-date 2026-09-29` + `scripts/_verify_five.py` → `OVERALL: PASS`.

### 1. Alignment.csv refresh + reference-file cross-check
- Re-pulled `Alignment.csv` from Snowflake after the user updated `OPX_ALIGNMENT`: 45 stores that previously showed "Unassigned" FOP/Director now correctly resolve (all to Kelly Sharpe / Betty Olvera); confirmed by diffing the freshly-pulled data against what was previously embedded in `fz_dashboard.html`.
- Cross-checked the user-supplied `Alignments - 15 zones.csv` against the live SQL pull: 114 stores where the reference file has a real OA/Zone/FOP/Director value and the SQL join returns null — **zero true conflicts** (no case where both sources have a value and disagree). 29 stores in the reference file don't exist in `DSC.ALIGN_DIM_V1` at all (confirmed directly against the source table, not just excluded by the query's `WHERE` clause) — likely closed/decommissioned stores lingering in that reference file. 3 stores are in the SQL pull but not the reference file.
- Found and fixed a genuine cross-report inconsistency: the reference file still has this franchisee as **"GARRETT MCGINN"**; the SQL pull already has it as **"DONALD RIZZIE"** (corrected upstream in Snowflake since the original pull); the rest of the dashboard has standardized on **"DON RIZZIE"** (see the `_fran_mask`/"Franchisee normalization (2026-09)" comment near the top of `generate_reports.py`, and the OA-remap alias list further down). `load_alignment_data()` now folds both "GARRETT MCGINN" and "DONALD RIZZIE" into "DON RIZZIE" so the Alignment tab agrees with the rest of the app.

### 2. `MANUAL_ZONE_OVERRIDES` (Python dict) — superseded by item 3 below, same day
- Added a Python-side `MANUAL_ZONE_OVERRIDES` dict in `generate_reports.py` as a stopgap for the 118 stores unmapped under the `OPX_ALIGNMENT`-only join (see item 1). **Removed later the same session** once it turned out Snowflake already has a real `AXC1195.MANUAL_ZONE_OVERRIDES` table for exactly this purpose — see item 3. Left here only so the session history makes sense; there is no Python-side override dict in the current code.

### 3. Rewrote the Alignment.csv SQL — `OPX_ALIGNMENT` was the wrong join target
- The user pointed out two more tables exist: `AXC1195.MANUAL_ZONE_OVERRIDES` (542 rows, real manual override table) and `AXC1195.STORE_ZONE_MAP` (5,014 rows, auto-computed). Querying Snowflake directly: **0** of the 118 unmapped stores exist in either table (so the unmapped list itself was accurate), but **364** open stores have a Zone in `OPX_ALIGNMENT` that actively **disagrees** with `STORE_ZONE_MAP` — a correctness problem 3x bigger than the coverage gap, invisible from the CSV alone.
- The user supplied the actual production join pattern: Zone comes from `MANUAL_ZONE_OVERRIDES ∪ STORE_ZONE_MAP` (latest `UPDATED_TS` wins), OA is derived *from* Zone via `AXC1195.ZONE_OA_MAP` (a clean 15-row 1:1 lookup — OA is not a per-store field at all), FOP comes from `AXC1195.OPX_FRAN_FOP_MAP` keyed by franchisee name (`IS_ACTIVE = 1`, latest `UPDATED_TS`), and Director comes from `AXC1195.OPX_FOP_DIRECTOR_MAP` keyed by FOP name (same pattern). None of these go through `OPX_ALIGNMENT`.
- Rewrote and tested the corrected query against Snowflake: unmapped stores dropped from 119 to 0 (the "1" remaining is the pre-existing single garbage all-null row already filtered out elsewhere), confirming this is the right join. See the updated SQL in the `Alignment.csv` section above.
- Removed the Python-side `MANUAL_ZONE_OVERRIDES` dict from `generate_reports.py` (item 2) — it duplicated a mechanism that already exists correctly in Snowflake. Any future store-mapping gap should be fixed by adding a row to `AXC1195.MANUAL_ZONE_OVERRIDES` directly, not by editing this codebase.
- Also tried to fix the repeated Snowflake SSO browser popups: installed `keyring` (silences the "cannot cache id token" warning) and tested `client_store_temporary_credential=True` explicitly — neither stopped the browser from reopening on every connection. This points to ID-token caching needing to be enabled at the **Snowflake account level** (an admin-side security-integration setting for external-browser SSO), not something fixable from the client. Flagged for the user rather than spending further turns on client-side workarounds.

### 4. Fixed slow page load — root cause was the external Google Fonts `@import`, not the embedded data size
- User asked whether the ~18 MB `fz_dashboard.html` file (largely `FOP_DATA`, now also `ALIGNMENT_DATA`) could be made to load faster. Measured first rather than guessing: in a headless-browser test harness, actually parsing all 16 MB of `FOP_DATA` as a JS object literal took a consistent **33-42 ms** — the embedded-data hypothesis was wrong.
- Isolated the real cause with a controlled A/B test: the same file with only the `@import url('https://fonts.googleapis.com/...')` line removed loaded in **5-13 ms** across three runs, vs. a wildly inconsistent **2.6-33 seconds** with it present (this environment has unreliable outbound network access, so the import's DNS/connection resolution is what stalls the page — a corporate VPN or firewall that blocks/throttles `fonts.googleapis.com` would cause the same thing on a real machine).
- Removed the identical `@import` line from **all five** reports (`fz_dashboard.html`, `zone_scorecards.html`, `leadership_summary.html`, `leadership_brief.html`, `rising_star.html`) — same line, same problem, in every one. Font-family declarations already end in generic fallbacks (`sans-serif`/`monospace`), so removal is a graceful, safe degradation (loses the distinctive Oswald/Inter/IBM Plex Mono look, gains zero external network dependency — actually closer to the reports' own "self-contained, share as a file attachment" design goal from `PRESENTATION.md`).
- Verified: `scripts/_verify_five.py` → `OVERALL: PASS` after regenerating through the normal pipeline (the removal survives `replace_data_block`/`_replace_month_refs` since those only touch the data consts and month text, not the `<style>` block). Re-measured the real `fz_dashboard.html` post-fix: consistent 5-10 ms load across three runs.
- **Follow-up:** the font fix wasn't the whole story — user reported the page shell now loads fast but the full page (and clicking into Alignment) still took several seconds. Turned out my in-page `performance.now()` timers had been measuring the wrong thing (see item 5), which sent the investigation down the wrong path before landing on the real fix (item 6).

### 5. `JSON.parse("...")` data embedding — kept, but couldn't prove it was the fix
- Root-cause theory: a browser must fully parse an entire `<script>` block as JS grammar before any statement in it runs, so a `performance.now()` marker placed *inside* that same script can only measure post-parse execution time, not the parse itself — explaining why FOP_DATA's JS-object-literal parse looked like "33-42ms" in item 4's measurement when the real cost sits earlier, invisible to that marker.
- Changed `replace_data_block()` in `generate_reports.py` to emit `const NAME = JSON.parse("...");` (a string literal) instead of `const NAME = {...};` (a raw object literal) — V8's JSON parser is established to be faster than the full JS grammar for equivalent multi-MB nested data. Implementation detail: this has to stay a single statement, not a separate `<script type="application/json">` tag — these templates keep one shared `<script>` block holding every data const *and* all the page's JS logic together, and a first attempt at the separate-tag approach corrupted that shared block (left fragments like `const REPORT_YEAR = 2026;` sitting as stray visible page text outside any script tag) and had to be repaired by hand across all 5 files before retrying with the single-statement form. Escaping: `</` → `<\/` (valid JSON string escape) so a data value can't prematurely close the `<script>` tag, then the whole result is JSON-encoded a second time to produce a valid, safely-escaped JS string literal (double-encoding a string is always safe to embed this way).
- Updated `scripts/_verify_five.py`: several checks searched for raw quoted JSON keys (e.g. `'"accuracy"'`); with the payload now living inside a string literal, those keys appear escaped (`\"accuracy\"`) in the file text. Added `has()`/`cnt()` helpers that check both forms. Checks against unquoted text or single-quoted JS code (HTML tags, hand-written JS identifiers) were already unaffected and didn't need changing.
- Re-measured properly with the browser's native Navigation Timing API (`domContentLoadedEventEnd`) instead of a hand-placed marker — this showed **no reliable improvement** from the JSON.parse change in isolation (object-literal ~3.3-4.6s vs JSON.parse ~4.1-4.5s domContentLoadedEventEnd, overlapping/noise-level), and the file grew ~8% (19.7MB vs 18.2MB) from the double-escaping overhead. Asked the user whether to keep or revert given the change is safe/verified-correct but unproven; they said keep it (low risk, matches established practice). It stays in, but item 6 is the change that actually moved the needle.

### 6. The real fix: split ~15 MB of drill-down-only data out of the initial load
- Measured exactly where `FOP_DATA`'s ~16.6 MB went (serialized size per field): **`store.p` alone was 10.1 MB (61%)** — the raw operational-metrics object `metricPanel()` needs for the Delivery/Business sections. Combined with `ns`, sentiment trend arrays (`osat`/`speed360`/`accuracy`), component star history (`cw`/`cs`/`cb`/`ch`/`cf`), `ct`, `lv`, `lg`, and `top`, **~15 of the 16.6 MB is data only ever read once a user drills into a specific franchisee or store** — the default Portfolio Overview only needs per-franchisee aggregates (~1 MB).
- Also found and dropped `sssg`/`sstg` as dead per-store fields entirely (confirmed via grep: nothing reads `store.sssg` directly — the real growth numbers come through the separate `storeGrowth()` lookup / quintile-bucket structures).
- **Design decision, confirmed with the user:** genuinely deferring this data requires moving it out of the single HTML file into a companion file, since a browser can't avoid scanning bytes that are present in the document regardless of when they're parsed. This breaks the "share as one email attachment" promise for the detail layer specifically. User hosts on GitHub (not emailing a lone .html), so approved the split as long as both files just need to stay together in the repo.
- Implementation: `DETAIL_STORE_FIELDS` + `_build_fop_store_list()` in `generate_reports.py` split each store entry into a lightweight summary (kept in `FOP_DATA`) and a detail record (collected into `store_detail`, keyed by store id). `compute_fop_data()` returns `store_detail` as an extra key; `generate_fop_html()` pops it off *before* embedding `FOP_DATA` and writes it via the new `write_store_detail_js()` to `fz_dashboard_detail.js` (same `JSON.parse("...")` embedding as item 5, same escaping).
- `fz_dashboard.html`: added `ensureDetailLoaded(callback)` — dynamically inserts `<script src="fz_dashboard_detail.js">` the first time it's needed, and on load merges `STORE_DETAIL[store.s]` onto each existing store object via `Object.assign` so every existing function (`metricPanel`, component cards, export cards) keeps reading `s.p`/`s.cw`/etc. completely unchanged — no call site needed to learn about "maybe not loaded yet". Only two entry points needed gating: `showFranchisee` (shows a "Loading store details…" placeholder, then calls `renderStoreList` once loaded — this is also where `metricPanel` first runs, one level before an individual store click) and `showStoreDetail` (defensive re-entry guard, since in normal navigation it's only reachable after `showFranchisee` already gated). `exportCardsPNG`/`fzCardHTML` and `exportFranchiseesCSV` needed no changes — verified their only read paths are already behind one of the two gates, or (for the CSV export) only touch summary fields that were never moved.
- **Result:** `fz_dashboard.html` dropped from 19.7 MB to **5.37 MB** (73% smaller); `fz_dashboard_detail.js` (13.8 MB) carries the rest, loaded once on demand. Measured with the same Navigation Timing metric as item 5's (inconclusive) test: `domContentLoadedEventEnd` went from ~3.3-4.6 **seconds** to a consistent **124-184 ms** — this time a real, unambiguous, order-of-magnitude win.
- Verified end-to-end in a real browser: before drilling into a franchisee, `store.p` is `undefined`; after `showFranchisee()`, it's populated with real data (confirmed 41 keys) and `metricPanel()` renders correctly with it; the Alignment tab (which never touches `FOP_DATA`'s store detail, only `ALIGNMENT_DATA`) is completely unaffected (4,666 rows, unchanged). `scripts/_verify_five.py` → `OVERALL: PASS`.
- **Deployment note:** `fz_dashboard_detail.js` must ship in the same folder as `fz_dashboard.html` (same GitHub repo path) — the dashboard degrades gracefully without it (drill-down views just render with those fields absent, via `el.onerror`), but won't show store-level metric panels, component history, or sentiment trends.

### 7. Exported PNG cards: metric-panel trendlines now always show, with a mode-specific reference line
- Request: exported restaurant cards should always show a trendline for the operational/business metric-panel sparklines (previously suppressed entirely in Last Month view, per the 2026-09-29 "per-view trendlines" fix — that fix stays correct for the *live* dashboard, this is export-only). YTD should additionally show a dashed reference line at the average across all months; Quarterly a dashed reference line at the last-3-months average; Last Month needs no extra line since the sparkline's existing endpoint dot already marks the latest point.
- `metricPanel(stores, title, forExport)` gained a third parameter. When `forExport` is true it always uses the full 8-month series (`_mSeriesFull`, new helper — the unconditional version of `_mSeries`) instead of the LM/LQ-trimmed one, and computes a reference value via the new `_seriesAvg()` helper: `null` for Last Month, average of the last 3 months for Quarterly, average of all months for YTD. Both the headline number (`_mNow`) and the card's Monthly/Quarterly/YTD label are untouched — only the graph changed.
- `sparkline()` gained an optional 5th `refValue` parameter — when set, draws a dashed horizontal `<line>` (`stroke-dasharray="2,2"`) at that value's y-position, extending the chart's min/max range to include it if needed so the line is never clipped. Fully backward-compatible: every other call site (component star cards, customer-sentiment cards, live-dashboard metric panels) omits the 5th argument and renders exactly as before.
- Only the two export call sites were changed to pass `forExport=true`: `fzCardHTML`'s and `zoneCardHTML`'s `metricPanel([s], ..., true)` calls. Scope was confirmed with the user: Component and Customer Sentiment mini-cards were intentionally left alone — they already always rendered a full trendline (never had the LM-suppression problem this request was about) — and Quarterly's reference line uses the same dashed style as YTD per the user's explicit choice, not a distinct solid style.
- Verified functionally in a real browser (synthetic store data, all three view modes, both files): Last Month → polyline only, no reference line; Quarterly and YTD → polyline **and** a dashed reference line, confirmed via direct SVG-markup inspection (`<line>` + `stroke-dasharray` present/absent exactly as expected per mode).
- **Found and fixed a real, unrelated bug while regenerating:** `replace_data_block()`'s "already-converted `JSON.parse(...)`" detection (from item 5) required a literal `");` to mark the end of the old value — but on a second+ regeneration pass it had been emitting output with no explicit trailing `;` at all (relying on JS's automatic-semicolon-insertion, which is syntactically valid but didn't match the literal string my own detection was searching for). This surfaced as `WARNING: Found 'JSON.parse(' for 'MONTHS' but couldn't locate its closing...` for the small `MONTHS`/`DATA`/`BRIEF` consts in three files (not the huge ones that don't get re-converted as often). Fixed the detection to accept a bare `")` with no semicolon too, and to always emit an explicit `;` going forward regardless of what it found — verified idempotent across two consecutive regenerations with zero warnings either time.

### 8. Exported PNG cards (Franchisee Dashboard only): added the system quintile badge
- Scoped to `fz_dashboard.html`'s `fzCardHTML` — `zone_scorecards.html` has no quintile feature at all (no `store_quintiles` data, no `.quint-badge` CSS, nothing to add there without building the feature from scratch, which wasn't asked for).
- Added `fzQuintStrip(s)`, rendered next to the existing score strip (`fzScoreStrip`) in the card header: a "Sys Quintile" label over the same `quint-badge q#` badge used in the franchisee store-list table, via the existing `storeQuint(s.s)` lookup (`FOP_DATA.store_quintiles[_quintWindow][s.s]`) — no new data plumbing needed, the quintile assignment was already embedded, just not surfaced on the export.
- Verified end-to-end in a real browser with real data: store #036622 resolves to Q2 via `storeQuint()`, and the exported card HTML contains both the "Sys Quintile" label and the matching `quint-badge q2` element. All 5 reports regenerated, `scripts/_verify_five.py` → `OVERALL: PASS`.

### 9. Trendline fix (item 7) extended to the live on-screen metric panel, not just the PNG export
- User reported "not seeing sparklines on Last Month" by pasting the text of a metric panel visible directly on the page — confirmed via headless re-test (same exact navigation they used: FOP "Noel Pelayo" → franchisee "JESSICA BERGEN ELLIOTT") that the *exported PNG* already had the trendline correctly (polyline + endpoint dot present, 0 reference lines for Last Month, dashed reference line present for Quarterly/YTD) — the mismatch was that item 7 had deliberately scoped the always-show-trendline behavior to the export-only `forExport` path, leaving the live dashboard's metric panel (shown in `renderStoreList`/`showStoreDetail` before any export) on its original LM-suppressed behavior. Confirmed with the user they wanted the live view to match the export, not the reverse.
- Removed the `forExport` parameter from `metricPanel()` entirely in both `fz_dashboard.html` and `zone_scorecards.html` — the always-full-trendline + mode-specific dashed-average-line behavior is now unconditional, the only behavior, live or exported. Removed the now-unnecessary `, true` argument from the two export call sites (`fzCardHTML`, `zoneCardHTML`).
- Verified by reproducing the user's exact navigation path in the live (non-export) view: Last Month → 29 metric cards, all 29 with a trendline, 0 with a reference line (correct); YTD → 29 trendlines **and** 29 dashed reference lines. All 5 reports regenerated, `scripts/_verify_five.py` → `OVERALL: PASS`.
- **Debugging note for next time:** the earlier false leads (checking for exact `JSON.parse` escaping, testing stale-file theories, pixel-color-matching the rasterized PNG) were all legitimate things to rule out given the symptom description, but the fastest path to the real cause was asking the user to paste what they were actually looking at — it immediately showed this was the live DOM, not an exported file.

### 10. Per-store selection before PNG export, with quintile quick-select
- Request: large franchisees shouldn't force an all-or-nothing export — someone showing off a portfolio to a franchisee usually wants a curated subset (though sometimes the whole thing), and picking by system quintile is a natural way to narrow down.
- `fz_dashboard.html`, `renderStoreList()`: added a checkbox column to the franchisee store-list table (plus a header "select all" checkbox) and a selection toolbar above it — **All** / **None** buttons, one quick-select button per quintile actually present among this franchisee's stores (`Q1`-`Q5`, styled with the same `.quint-badge` colors used elsewhere), a live "N of M selected" counter, and the export button (moved here from the franchisee title line, renamed "Export selected (PNG)").
- **Defaults to everything selected** — exporting with no changes still exports the whole franchisee in one click, same as before this feature existed; narrowing down is opt-in.
- Select All/None and the quintile buttons only act on currently-**visible** rows, so they compose with the existing search/region/area filters (e.g. filter to a region, then "All" selects just that region). Checkbox state itself is untouched by filtering — hiding a row via search/filter never silently deselects it.
- New functions: `toggleAllVisibleStores(checked)`, `selectQuintileStores(q)` (reads each row's `data-quint` attribute, set from the existing `storeQuint()` lookup), `updateExportCount()` (also keeps the header checkbox in sync — checked only when every row is checked), `exportSelectedCardsPNG()` (reads all checked `.store-select-cb` elements regardless of visibility, maps back to store objects via `window.__cardStores`, and refuses with an alert rather than silently exporting nothing if none are selected).
- Checkbox clicks use `event.stopPropagation()` on their containing `<td>` so checking a box doesn't also trigger the row's `showStoreDetail()` navigation.
- Verified end-to-end on the largest real franchisee in the dataset (990 stores, picked programmatically as a stress test): default-all-selected, None, All (with header-checkbox sync), quintile select (Q5 → exactly 63 matching stores, verified against a manual count), export call receiving exactly that 63-store subset (not all 990), and exporting with zero selected correctly alerting instead of calling the export function. All 5 reports regenerated, `scripts/_verify_five.py` → `OVERALL: PASS`. Scoped to `fz_dashboard.html` only, per the request's franchisee-specific wording — `zone_scorecards.html`'s export (organized by DMA/Area, not franchisee) was left untouched.

---

## Reporting session changelog — 2026-09-29

All changes below are **durable**: they live in `generate_reports.py`, `fz_dashboard.html`, `zone_scorecards.html`, and `leadership_summary.html`. Verified after `python generate_reports.py --run-date 2026-09-29` + `scripts/_verify_five.py` → `OVERALL: PASS` (esprima-clean).

### 0. LLM backend switched from OpenCode/Ollama to the Claude API
- `generate_reports.py` no longer talks to a local OpenCode server (`_detect_opencode_url`, `cleanup_session`, session-based HTTP calls all removed). `call_claude()` (formerly `call_opencode_server`) now calls `client.messages.create(...)` via the official `anthropic` Python SDK.
- **Credentials:** set `ANTHROPIC_API_KEY` in `.env` (or run `ant auth login`). If the key is an org key not scoped to a single workspace, also set `ANTHROPIC_WORKSPACE_ID` in `.env` — read only from `.env` itself (`_ENV_FILE_VARS`), never from an ambient shell/session variable of the same name, so an unrelated `ANTHROPIC_WORKSPACE_ID` in the calling environment can't get silently attached to every request.
- **Model:** defaults to `claude-sonnet-5-5` (override via `ANTHROPIC_MODEL`) — the right tier for short, structured executive narratives generated from data, not open-ended reasoning.
- **Effort / `max_tokens` tuning (important if you see silent "LLM call failed" with no error text):** Claude's adaptive thinking spends part of `max_tokens` on hidden thinking tokens before writing the visible response. The batched calls (`summarize_zones` — up to 4 OA summaries per call, `summarize_fops` — all FOPs in one call) need enough headroom for several full 3-paragraph summaries plus thinking; they're set to `max_tokens=8000`. All calls default `effort="low"` in `call_claude()` (templated business writing, not hard reasoning) to keep the thinking budget small. If you see the diagnostic log line `LLM response had no usable content (stop_reason=..., output_tokens=...)`, raise that call site's `max_tokens` rather than assuming the prompt is broken.
- Auth/permission failures (bad or unscoped key) are not retried — `call_claude` sets `_LLM_UNAVAILABLE = True` on the first one so the remaining ~20 summary calls in a run fail fast instead of each retrying a doomed request.
- Delete `_summaries.json` after any change to summary-generation logic (prompts, model, effort, etc.) — the cache only auto-invalidates when the report's month range changes, not when the generation code changes.
- `USER_GUIDE.md`, `brand_standards.md` requirements sections updated from `OPENCODE_SERVER_PASSWORD` to `ANTHROPIC_API_KEY`.

### 1. `REMAINING_ISSUES.md` four-item pass
Implemented and verified all four previously-open items: hide AI-summary box on franchisee drill-down, per-view (LM/LQ/YTD) sparklines on metric cards, raw value alongside star score for Win/Speed/Hutbot component cards, and exported cards stating the actual report timeframe (`REPORT_YEAR` constant + `_periodLabel()` helper). See `REMAINING_ISSUES.md` for the full breakdown.

### 2. OA names → Zone names in AI-generated report text
- Added `OAs.xlsx` (OA, Latitude, Longitude, City, 15 Zone, 24 Zone) as the OA→Zone name lookup. `generate_reports.py` loads it into `OA_ZONE_MAP` and exposes `zone_name_for(oa)` (falls back to the OA's own name if the file or a mapping is missing).
- `generate_fallback_summary`'s National Insight narrative, and the `zone_rank` / `zone_rank_compact` data fed to the LLM narrative, now carry a `"zone"` field alongside `"oa"` — both the deterministic fallback text and the LLM-written summary now refer to zones by their Zone name (e.g. "Pacific Northwest", "Deep South") instead of the OA's personal name.
- `leadership_summary.html` Zone Ranking table: header renamed `Zone (OA)` → `Zone`; each row shows the Zone name with the OA's name as a small muted sub-line for reference.
- `zone_scorecards.html`: OA dropdown options now read `"<Zone Name> — <OA Name>"` (value stays the OA key so drill-down/data lookups are unaffected); the `Zone:` footer line, breadcrumb, and portfolio subtitle/metric-panel title all show the Zone name (OA name kept in parens on the footer for reference).
- Per-OA `compute_single_zone` python dict (backing `zone_scorecards.html`'s `ZONES` const) also carries the new `"zone"` field.
- Ran with a stale `_summaries.json`: LLM/fallback summary text only refreshes when the cached `_version` changes (month range), so the cache had to be deleted once to force the National Insight / per-zone summaries to pick up the new zone-name text. Delete `_summaries.json` after any future change to summary-generation logic, not just after a data refresh.
- Follow-up (same day, during the Claude API migration below): the LLM-*written* per-zone 3-paragraph summaries (`summarize_zones`) still said "Danielle Hudson's 420-store portfolio" — the compact data passed to the model didn't carry a zone-name field, only the OA's name as the JSON dict key. Added `"zone_name": zone_name_for(oa)` to `oa_data[oa]` and an explicit system-prompt instruction to refer to the zone by `zone_name` in prose while keeping the OA's name only as the JSON key for mapping — confirmed fixed ("the Texas North / Oklahoma zone's monthly average rose...").

### 3. Franchisee Dashboard: keep quintile summary visible on franchisee drill-down
- `renderQuintiles()` (`fz_dashboard.html`) no longer hides `#quintSection` when `_state.level === 'fran'`. `quintScope()` already mapped the franchisee level to its parent FOP's quintile bucket, so the section now stays visible and shows that FOP-level breakdown as "up top" context while the store list below is franchisee-specific. (Supersedes the 2026-09-24 entry below, which had this hide as a deliberate design choice.)

### 4. New Alignment tab on the Franchisee Dashboard
- Added a `Portfolio` / `Alignment` tab bar to `fz_dashboard.html` (first tab UI in this file — wraps the existing drill-down content as `tabPortfolio`, adds `tabAlignment`).
- New optional input `Alignment.csv` (SQL to produce it is in this guide's "Exporting Data from Snowflake" section) — one row per open franchised store: franchisee, OA/Zone/FOP/Director assignment, DMA/Region/Area, mailing address, lat/long, rolling 3-month 5-Star average, and Tier. `load_alignment_data()` in `generate_reports.py` reads it (optional — empty tab if the file is missing) and `generate_fop_html` embeds it as `ALIGNMENT_DATA`.
- Sortable (click any header), filterable (dropdowns for Zone/FOP/Director/State/Tier + free-text search covering store #/franchisee/city/DMA/area/region), and exportable — the CSV export respects whatever filters are currently active and encodes them into the filename.
- Verified end-to-end: ran the SQL against Snowflake live (4,666 stores), confirmed the data embeds correctly, and confirmed tab-switch/filter/sort/export all work via a headless-browser test that drives the real page JS (not just a static DOM check).
- No LLM/Claude call anywhere in this tab — pure Snowflake → CSV → static HTML/JS.

### 4b. Fixed "High rack + high DaaS (9709%)" — double percentage scaling bug
- `metricPanel()`'s Delivery-section DaaS caveat (`fz_dashboard.html` and `zone_scorecards.html`, right after the metric card grid) reads `_dssV = _mNow(withP, MET_DEFS.find(x=>x.k==='dss'))`. The `dss` metric definition already carries `f:100`, so `_mNow`/`_mval` returns a value already on the 0–100 scale (e.g. `97.09` for 97.09% DaaS share) — same convention every other `u:'%'` metric card uses.
- The caveat block didn't know this: it compared `_dssV>=0.5` (a 0–1-fraction threshold, so it fired as "high DaaS" for almost any nonzero share) and displayed `(_dssV*100).toFixed(0)+'%'` (re-multiplying an already-scaled value) — `97.09 * 100 = 9709`, hence "High rack + high DaaS (9709%)".
- Fixed both files: threshold is now `_dssV>=50`, display is now `_dssV.toFixed(0)+'%'` (no second `*100`).
- Verified via a headless-browser unit test of `metricPanel()` with synthetic per-month `p` data: 97% DaaS → "High rack + high DaaS (97%)"; 20% DaaS → "High rack + low DaaS (20%)" — both branches now read correctly.

### 5. Claude API usage audit — confirmed scope, fixed a real "once a month" gap
- Audited every reference to the Anthropic client in the codebase: `_claude_client.messages.create(...)` is called from exactly one line, inside `call_claude()`, itself only ever invoked by the four summary-generation functions (`summarize_zones`, `summarize_leadership`, `summarize_fops`, `summarize_brief`). Nothing else — not the Alignment tab, not Snowflake, not any script in `scripts/` — touches the Claude API.
- Found and fixed a real gap: `summarize_brief`'s cache key embedded the literal `--run-date` (defaulting to *today's actual date* when not passed), unlike the other three functions which key only on the report's month range. That meant the Leadership Brief's 3 LLM calls fired fresh on every calendar day the script ran without an explicit, stable `--run-date` — not just when a new month's data landed. Fixed by keying `summarize_brief` on `_summary_version()` alone, matching the other three. Verified: regenerated three times with three different `--run-date` values (same month range) — after the fix, only the first run (transitioning off the old cache format) called the LLM; the next two both hit cache with zero new calls.
- **Net effect:** as long as the report's detected month range doesn't change, none of the four summary functions call the Claude API — regardless of how many times or with what `--run-date` the script is re-run. The LLM is only actually called when a new month's 5-Star data lands (i.e., ~once a month in the documented workflow), or after `_summaries.json` is deleted on purpose.

---

## Reporting session changelog — 2026-09-24 (Franchisee Dashboard export & toggle pass)

All changes below are **durable**: they live in `fz_dashboard.html` / `zone_scorecards.html` self-templates (the generator only patches data, never rewrites render JS). Verified after `python generate_reports.py --run-date 2026-09-15` + `scripts/_verify_five.py` → `OVERALL: PASS` (esprima-clean).

### 1. Quintile section at high level only
- `<section id="quintSection">` (`fz_dashboard.html:226`) — `renderQuintiles()` hides it and returns when `_state.level === 'fran'` (`:1477-1482`), shows otherwise. Quintile window buttons drive the same unified toggle.

### 2. Unified Monthly / Quarterly / YTD toggle
- `setViewMode(mode)` (`fz_dashboard.html:299`) sets **both** `_scoreMode` and `_quintWindow`, syncs the `.avg-mode-btn` and `.quint-win-btn` active states, then calls `refreshCurrentView()`.
- `setScoreMode(mode)` and `setQuintWindow(w)` both delegate to `setViewMode` — no more desynced windows.
- Default unified to **YTD**.
- `_mNow` quarterly is now the last 3 months: `_psum(stores, MONTHS.length - 3, null)` (Jun–Aug), matching `LQ_KEYS`.

### 3. Exported restaurant-card fixes (PNG)
- **Dark-background bug:** `elToBlob` now does `dv.appendChild(clone)` instead of moving child nodes (`fz:1713`, `zone:2612`) — preserves the card root's inline light background.
- **"undefined franchisee" label:** restaurant-header line now renders `s.f || _state.fran` and only adds the " · franchisee" suffix when a franchisee name exists (`fz:1778`).
- **Footer sigma callouts removed** from card footers and metric-panel footers (grep confirms 0 matches for `never averaged` / `never an average` / `Recomputed per level` in both files).

### 4. Documentation
- `REMAINING_ISSUES.md` added — four open items (AI-summary hide at franchisee drill-down, per-view trendlines, Score+Value on component cards, timeframe in exports) with exact line references and verification hooks.

---

## Reporting session changelog — 2026-09-15

All of the following are **durable**: they live in `generate_reports.py` (data + module-level constants) or in the self-template HTML files that the generator only patches (never rewrites the render JS, so hand-edits like the map tiles and paragraph renderer survive every regeneration).

### 1. Run-date on report titles (freshness)

- `leadership_summary.html` and `leadership_brief.html` — keep the run-date/freshness stamp (title shows the period; the report carries a `Run date:` line bound to the report's run label).
- `zone_scorecards.html`, `rising_star.html`, `fz_dashboard.html` — **no** run date in `<title>`. The generator never writes `<title>` (verified: 0 `<title>`-stamping code paths), so these stay clean on regeneration.

### 2. Rising Star map — tile provider

The map previously used `tile.openstreetmap.org`, which started blocking with the OSM tile-usage-policy screen (“Access blocked … osM.wiki/Blocked”). Now uses **CARTO light tiles** (no API key, allowed for dashboards):

```
https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png
```

Verified durable: regen re-produces the OSM-free tile block + CARTO URL.

### 3. National Portfolio Summary — paragraphing

The Portfolio narrative is no longer one `<br>`-joined wall of text. The renderer now groups sentences into real paragraphs:

- Narratives come back (plain text) from the LLM / cached `_summaries.json`.
- The leadership summary JS renders them as separate `<p>` blocks (`paras.map(...)`), readable instead of a single `<br>` wall.

### 4. Franchisee reassociation (data)

GARRETT MCGINN stores (and any legacy `DONALD`-mislabelled franchisee stores) are bound at generator level to OA **Kelly Sharpe** in `compute_fop_data`/`compute_fop` — applies on every regeneration, all reports. The store-level OA column no longer shows an unlinked/blank FOP for that franchisee.

### 5. Module-level constants (regen reliability)

- `MONTH_NAMES` is now a **module-level** dict (was function-local), so `generate_reports.py` no longer crashes with `NameError: MONTH_NAMES` when `--run-date` is omitted.
- `_MONTH_NAME` legacy helper retained for backward compatibility; the module-level `MONTH_NAMES` is the source of truth for all title/period month label lookups.

### 6. Scripts hygiene

- Root of `Reporting/` now contains only **`generate_reports.py`**.
- All one-off checkers / probes / sweep helpers were moved to **`scripts/`** (or deleted). Re-runnable verification helpers live there too (`scripts/_final_verify.py`, etc.).
- `brand_standards.md`, `USER_GUIDE.md`, and `PRESENTATION.md` remain the documentation set for this reporting folder.
