# 5-Star Reporting Suite — How & Why

---

## The Problem

The 5-Star program generates a huge volume of store-month data, but there was no consolidated view that connected it to roles, actions, and outcomes. Each role (OA, FOP, Director, Leadership) had different questions, all answerable from the same data, but the data wasn't shaped to their lens.

**The core insight:** One dataset, four perspectives.

---

## The Data Pipeline

```
5-Star.csv (monthly export)     Workshops.csv (optional, workshops)
    │                                   │
    └───────────────┬───────────────────┘
                    ▼
          generate_reports.py
                    │
           ├──► leadership_summary.html     (national health + watch list + workshops + per-FOP summaries)
           ├──► fz_dashboard.html           (Franchisee Dashboard — franchisee portfolio + Director/FOP drill-down)
           ├──► zone_scorecards.html        (per-OA deep dive + portfolio drill + workshop history)
           └──► rising_star.html            (Tier 2 targeting map + DMA×Franchisee groups + workshop history)
```

**Why a Python script?** The CSV is ~34K rows and growing. Doing this in Excel would be error-prone and slow. Python automates the join, filter, aggregation, and HTML generation in ~30 seconds. Drop the file, run the script, get four reports.

**Why self-contained HTML?** No server, no database, no login. Each .html file embeds its own data as a JSON constant. Open it in any browser, share it as a file attachment, it just works.

---

## The Four Reports, Mapped to Roles

### 1. `leadership_summary.html` — For Leadership

**Goal:** Know the overall health of the system. Where are the problems? Are fixes working?

**How leadership works:** They set the strategy — which zones need investment, whether training programs are paying off, and where to escalate. They don't need store-level detail; they need trends, risk concentrations, and a narrative they can carry into a meeting.

**What the report gives them:**

| Tab | Feature | Why it matters |
|---|---|---|
| Overview | National Insight | Narrative summary (LLM or fallback) of what happened, current state, and top priority — one flowing read they can quote |
| Overview | Zone Ranking | Which zone is best/worst; which director's territory needs attention. Gradient trend indicators (green = improving, red = declining, darker = more severe) |
| Overview | Tier Movement (Sankey) | Are stores flowing up or down across the system? |
| Overview | National Trend (chart) | Are overall scores improving month over month? Which components are dragging? |
| Overview | Binding chart | What's holding each tier back nationally — if Bootcamp stores are all bound on Win Score, that's strategic |
| Overview | FOP Summaries | Per-FOP 3-paragraph AI summaries (Past \| Present \| Future) showing portfolio shifts, risk counts, and recommended action |
| Default Watch | Defaulting/At-Risk/T1 Watch tables | Every store in trouble, sorted by severity, with OA and Franchisee — actionable to the individual store level |
| Workshops | Workshop Summary | Key metrics at a glance: workshops held, upcoming, stores improved, stores not improved — broken out by Boot Camp and Rising Star |
| Workshops | Workshop Effectiveness | Control vs. variable analysis for Boot Camp **and** Rising Star — did attending stores improve more than tier-matched stores that didn't? Control group = T1 stores (bootcamp) or T2 stores (rising star) at baseline month minus attendees. Validates the program investment |
| Workshops | Workshop History (date-aggregated) | Every workshop nationally, grouped by date and facilitator. Same-day workshops are grouped by Area Coach (FAREADESC), showing distinct blocks when multiple coaches host. Each store row shows post-workshop scores with improvement deltas, and sparkline trend. Drill down: Date → Area Coach → Individual stores |
| Workshops | Export CSV | Export all workshop data (filtered by type) with DATE, WORKSHOP_TYPE, AREA_COACH, STORE, BASELINE, 30d, 60d, 90d, CHANGE |
| Workshops | Franchisee Filter | Filter workshops by franchisee to isolate stores within a specific ownership group |
| Workshops | Per-FOP Summaries | Same FOP summaries from Overview, surfaced in the Workshops context |

**The leadership loop:**

```
Overview  → narrative health of the portfolio
           → zone ranking shows who needs help
           → binding shows what to fix
Default Watch  → shows who's in crisis
Workshops      → shows whether training investments are paying off
```

---

### 2. `fz_dashboard.html` — Franchisee Dashboard

**Goal:** Keep franchisees healthy and default-free.

**How FOPs work:** They manage the Franchisee relationship. If a franchisee's stores start defaulting, the FOP escalates with both the franchisee and the OA to build an action plan. They don't coach stores directly — they manage the portfolio.

**What the report gives them:**

| Tab | Feature | Why it matters |
|---|---|---|
| Portfolio Overview | All-franchisee portfolio | Defaults to the full portfolio view showing every franchisee across all FOPs, with FOP & Director columns — a national franchisee health dashboard |
| Director view | Director aggregate cards + franchisee list | Director sees their territory's health at a glance (stores, franchisees, risk counts) with every franchisee ranked by defaulting stores |
| FOP view | Per-FOP AI summary + franchisee table | FOP gets a 3-paragraph AI insight (Past \| Present \| Future) and every franchisee sorted by risk — actionable intelligence for the next check-in |
| Franchisee drill-down | Store list with search, status badges, trend arrows, Region & Area Coach filters | Before a franchisee meeting, pull up every store in trouble with scores, consecutive months, and FSCC/Brand failures. Filter by Region or Area Coach |
| Store Detail | Status banner + component breakdown | Clear language: "Default threshold met — immediate improvement plan required" with month-by-month component scores |

**Dynamic headline score:** The Average 5-star in the header updates as you drill down — national → director → FOP → franchisee — always showing the weighted average for your current selection. The Jan→Jun delta below it updates too.

**Score mode toggle:** LM / LQ / YTD buttons change how scores are computed across all views. LQ mode computes a rolling 3-month average.

**Trend arrows:** Gradient coloring — darker green = stronger improvement, darker red = steeper decline. Severity thresholds: >0.3 slope = strong, >0.15 = moderate.

**The default framework:**

Status is recomputed from store data at render time (not from the CSV), using the consecutive-months field from the data:

| Status | Criteria | Action |
|---|---|---|
| **Defaulting (dl)** | 3+ consecutive months < 2.0★ OR 4+ of last 5 | FOP escalates, OA builds plan |
| **At Risk (ar)** | 2 consecutive months < 2.0★ | Preventative intervention needed |
| **T1 Watch (tw)** | Latest score 2.0–2.5★ (Bootcamp but not default zone) | Monitor, address before it worsens |
| **OK** | Everything else | Business as usual |

**Why this matters:** A defaulting store isn't just a 5-Star problem — it's a Brand Standards failure. Per policy, repeated failures can affect franchise agreements. The FOP is the early warning system.

---

### 3. `zone_scorecards.html` — For OAs

**Goal:** Raise low-tier stores, promote top-tier stores.

**How OAs work:** They train shoulder-to-shoulder in markets that need the most help. They run Bootcamp workshops by DMA, focusing on an area coach and their restaurants per workshop. Post-workshop, they compare each store's pre-workshop trajectory against its post-workshop scores to measure whether the workshop moved the needle — each store serves as its own baseline.

**What the report gives them (4 tabs):**

| Tab | Feature | Why it matters |
|---|---|---|
| Overview | Goal Tracker | Shows if they're on pace for T1 reduction, T3 growth, and gross stores moved up (target: 75) |
| Overview | Area & Franchisee Spotlight | Tells them **where to go** — lowest/highest areas and best/worst franchisee |
| Overview | Binding chart | Per-tier breakdown of what's holding stores back — each store's worst component is its binding constraint. If 54% of Tier 1 are bound on Speed, that's where to focus coaching, not Brand |
| Overview | Default Watch | Quick check: any stores at risk of falling through the floor? |
| Portfolio | Drill-down (OA → DMA → Area → Store) | Before a workshop, drill into a DMA and see every store with scores, status, and trends |
| Portfolio | Store Detail | During a workshop, pull up a store's component scores |
| Boot Camps | Past Workshop History | Completed workshops grouped by date with baseline score, post-score trend sparkline, and delta. Drill down to per-store Pre Score / Post Scores / Delta |
| Boot Camps | Future Workshop List | Upcoming workshops with store count, Area Coach(s), and average baseline score only — no post-scores until the workshop is past |
| Targeting | Bootcamp Targeting | **Where to go** — which area/franchisee has the most Tier 1 stores by count and concentration, with binding focus bars |

**Dynamic headline score:** The Average 5-star updates to the selected zone's weighted average. The Jan→Jun delta updates too.

**Trend arrows:** Gradient coloring — darker green = stronger improvement, darker red = steeper decline.

**The tier system they care about:**

```
< 2.5★  → Bootcamp  (needs intervention)
2.5–4.0 → Rising Star (target for promotion)
≥ 4.0   → Top Tier   (protect and replicate)
```

**The binding logic:** Whichever of the five components (Win Score, Speed, Brand, Hutbot, FSCC) has the lowest score determines what's holding the store back. That tells the OA what to coach on.

**Baseline logic (Boot Camp):** Each workshop entry carries a baseline score computed as an average of available 5-star data before the workshop. The anchor month depends on the workshop day: on/after the 15th → anchor = workshop_month - 1 (prior month's data is available); before the 15th → anchor = workshop_month - 2 (need to go back one more). Baseline = average of available months from (anchor-2, anchor-1, anchor) — uses whatever data exists (1, 2, or 3 months), don't require all 3. Follow-ups start the month after the workshop: 30-day (month 1 after), 60-day (average of months 1–2 after), 90-day (average of months 1–3 after) — also uses available months. Export includes CHANGE column (latest check-in minus baseline).

---

### 4. `rising_star.html` — Rising Star Targeting (Cross-Zone)

**Goal:** Identify the best DMA×Franchisee combinations for Rising Star workshops by aggregating Tier 2 stores nationally, independent of OA zone boundaries.

**Why a separate page:** A franchisee's stores within a single DMA may cross OA zone boundaries, but they should be targeted together. This page groups by DMA×Franchisee regardless of zone, so the right people are in the room.

**What the report gives them:**

| Tab | Feature | Why it matters |
|---|---|---|
| Targeting | National map of Tier 2 stores | Every Tier 2 store plotted with binding-constraint coloring — see the national distribution at a glance. Click a legend item to filter to that binding only (click again to show all) |
| Targeting | All DMA×Franchisee groups | Every DMA×Franchisee combination with Tier 2 stores, ranked by count with focus bars showing the dominant binding component and workshop status (Completed/Scheduled/None) |
| Targeting | Concentration rate | What % of this franchisee's stores in this DMA are Tier 2 (high rate = better ROI per workshop) |
| Targeting | Multi-zone flag | When a DMA×Franchisee group spans multiple OAs, flagged so scheduling gets the right coaches together |
| Workshops | Rising Star Workshops | Date-grouped cards matching Leadership Summary format — gold background, expand to Area Coach cards with store count, then drill to individual stores with baseline, 30/60/90 post scores, sparkline trend, and deltas |

---

## Key Design Decisions

**1. Why the threshold is 2.0★ for default, not 2.5★**
2.5★ is the Tier 1 boundary (Bootcamp). But per the Brand Standards Manual, < 2.0★ is a "Failure to Satisfy." Using 2.0★ for default detection aligns with policy, not just the tier system.

**2. Why consecutive months matter**
A store that scores 1.9★ in May is different from one that's been below 2.0★ since January. The consecutive count (`cu` in the data) distinguishes a bad month from a systemic problem.

**3. Why binding = lowest component**
A store's overall score is a weighted average. But the lowest component tells you what to fix. If Speed is the binding constraint, don't coach on Brand — coach on Speed. This is the actionable insight.

**4. Why four files instead of one**
Each role has a different entry point. Leadership doesn't care about DMA drill-down. OAs don't care about franchisee portfolios. Four files = four lenses, zero friction. The Rising Star page is intentionally separate because it's zone-agnostic — it cuts across OA boundaries by design.

**5. Why the Store List is optional**
The Store List was originally required for Area/LatLong/FOP fields. Now the 5-Star CSV carries those columns directly, so the Store List join only overrides values when present. Simpler pipeline, fewer dependencies.

**6. Why the Rising Star map is filterable by binding**
The map legend is clickable — clicking a component filters to stores bound by that component only, clicking again shows all. This lets leadership quickly answer "where is Win Score the biggest problem?" without scanning the full map.

---

## Monthly Cadence

```
1st-5th: Scores close → export 5-Star.csv + Workshops.csv
5th:     python generate_reports.py
         → four HTML files ready
         → share links or attach files
```

No database, no server, no credentials needed — even LLM summaries are optional (fallback summaries are data-driven). The reports are self-contained — email them, post them, open from a shared drive.

---

## The FSCC Gap (Elevated)

One known issue: the Brand Standards Manual says a failed FSCC should cap a store at 1.0★. The actual weighted-average formula lets FSCC be overridden by strong scores in other components. This means some stores with failing food safety scores appear in Tier 2 or 3. The reports reflect the formula as-calculated, not the policy override. **This is flagged for escalation — the reports are ready to implement an FSCC override as soon as policy alignment is decided.**
