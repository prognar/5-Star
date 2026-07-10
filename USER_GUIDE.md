# 5-Star Reports — Quick Start Guide

Four HTML dashboards, generated from `5-Star.csv`. Open in any browser.

---

## 1. `fop_dashboard.html` — FOP Portfolio View

**Audience:** FOPs (Franchise Operations Partners) and Directors.

**What it does:** Groups stores by Director → FOP → Franchisee so you can see which franchisees in your portfolio have stores in trouble.

**Navigation:**

| Step | What you see |
|---|---|
| Select a **Director** | Aggregate stats for that director's entire territory + table of their FOPs |
| Click a **FOP** row (or select from dropdown) | That FOP's summary (stores, franchisees, defaulting/at-risk/T1 counts) + table of their franchisees |
| Click a **franchisee** row | Store list for that franchisee with status badges, scores, trend arrows |
| Click **Detail** on a store | Full component breakdown (Win Score, Speed, Brand, Hutbot, FSCC) with monthly scores and sparklines |

**Key columns in the franchisee table:**
- **Defaulting / At Risk / T1 Watch** — count of stores in each status within that franchisee
- **Cons** — consecutive months under 2.0★
- **FSCC / Brand** — count of months the component scored below 2.0★

**Color cues:** Red = defaulting, Amber = at risk, Red outline = T1 watch. Status banners in store detail explain what each means and what action is needed.

---

## 2. `leadership_summary.html` — National Executive View

**Audience:** Leadership, Directors, Strategy.

**What it does:** National roll-up of all 15 zones in one page. Two tabs.

### Overview tab
- **Goal Tracker** — how the business is pacing toward annual T1 reduction, T3 growth, and upward movement targets (green = on pace, amber = behind, red = moving wrong way)
- **Tier Movement** — Sankey diagram showing how stores flowed between tiers Jan→May
- **Zone Ranking** — all 15 zones sorted by current average, with movement arrows
- **National Trend** — 5-month line chart of overall average and each component
- **Binding chart** — for each tier nationally, which components are the binding constraint (lowest score)

### Default Watch tab
- **Sortable table** of every defaulting, at-risk, and T1-watch store nationwide
- Columns: Store ID, OA, Franchisee, DMA, Score, Status, Consecutive months, FSCC/Brand fails
- Sorted by severity (defaulting first, then at-risk, then watch) then score ascending

---

## 3. `zone_scorecards.html` — OA Zone Scorecard

**Audience:** OAs (Operations Assistants / Zone Managers).

**What it does:** Per-zone deep dive. Select a zone from the dropdown. Two tabs.

### Overview tab
- **Goal Tracker** — same goals as leadership but for this zone
- **Tier Cards** — breakdown of each tier (count, average, binding component, stay/up/down counts)
- **Sankey** — tier flow for this zone
- **Trend chart** — zone-level 5-month trend with component lines
- **Binding chart** — per-tier binding percentages
- **Bootcamp Areas** — which area/franchisee combinations have the most Tier 1 stores, with binding focus bars
- **Default Watch** — this zone's defaulting/at-risk/T1-watch stores
- **Best Improvers** — stores with the biggest Jan→May score increase

### Portfolio tab (OA Portfolio Drill-Down)
- Drill-down: **OA → DMA → Area → Store → Component**
- Toggle between **Monthly / Quarterly / YTD** view
- Each level shows: group average, T1/T2/T3 counts, **Status badges** showing how many stores in that group are defaulting/at-risk/watch
- Click any row to drill down. Breadcrumb navigation at top to go back up.
- Click **Detail** on a store for component breakdown with sparklines

**Status badges:** Red = DEFAULT (3+ consecutive months <2.0★), Amber = AT RISK (2 consecutive), Red outline = WATCH (2.0–2.5★)

---

## 4. `rising_star.html` — Rising Star Targeting

**Audience:** OAs and FOPs looking for growth opportunities.

**What it does:** Maps where Tier 2 (Rising Star) stores cluster, so you can target coaching to push them to Tier 3.

- **Map** — each point is a Tier 2 store. Color-coded by binding component. Hover for store details.
- **Top 30 DMA × Franchisee table** — groups with the most Tier 2 stores, ranked by count. Shows each group's binding focus (which component is holding them back).
- **Headline number** — total Tier 2 stores nationally

---

## Monthly Update

```powershell
# Drop new 5-Star.csv into the Reporting folder, then:
python generate_reports.py
# Open any of the 4 HTML files — they're self-contained.
```

No other files needed. The Store List CSV is optional (only needed if lat/lon for the map is required).
