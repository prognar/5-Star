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
           ├──► fop_dashboard.html          (FOP/Director franchisee portfolio + per-FOP AI summaries)
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
| Overview | Zone Ranking | Which zone is best/worst; which director's territory needs attention |
| Overview | Tier Movement (Sankey) | Are stores flowing up or down across the system? |
| Overview | National Trend (chart) | Are overall scores improving month over month? Which components are dragging? |
| Overview | Binding chart | What's holding each tier back nationally — if Bootcamp stores are all bound on Win Score, that's strategic |
| Overview | FOP Summaries | Per-FOP 3-paragraph AI summaries (Past \| Present \| Future) showing portfolio shifts, risk counts, and recommended action |
| Default Watch | Defaulting/At-Risk/T1 Watch tables | Every store in trouble, sorted by severity, with OA and Franchisee — actionable to the individual store level |
| Workshops | Workshop Effectiveness | Control vs. variable analysis for Boot Camp **and** Rising Star — did attending stores improve more than similar stores that didn't? Validates the program investment |
| Workshops | Workshop History (date-aggregated) | Every workshop nationally, grouped by date, with per-store drill-down and sparkline trends |
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

### 2. `fop_dashboard.html` — For FOPs and Directors

**Goal:** Keep franchisees healthy and default-free.

**How FOPs work:** They manage the Franchisee relationship. If a franchisee's stores start defaulting, the FOP escalates with both the franchisee and the OA to build an action plan. They don't coach stores directly — they manage the portfolio.

**What the report gives them:**

| Tab | Feature | Why it matters |
|---|---|---|
| Portfolio Overview | All-franchisee portfolio | Defaults to the full portfolio view showing every franchisee across all FOPs, with FOP & Director columns — a national franchisee health dashboard |
| Director view | Director aggregate cards + franchisee list | Director sees their territory's health at a glance (stores, franchisees, risk counts) with every franchisee ranked by defaulting stores |
| FOP view | Per-FOP AI summary + franchisee table | FOP gets a 3-paragraph AI insight (Past \| Present \| Future) and every franchisee sorted by risk — actionable intelligence for the next check-in |
| Franchisee drill-down | Store list with search, status badges, trend arrows | Before a franchisee meeting, pull up every store in trouble with scores, consecutive months, and FSCC/Brand failures |
| Store Detail | Status banner + component breakdown | Clear language: "Default threshold met — immediate improvement plan required" with month-by-month component scores |

**The default framework:**

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

**How OAs work:** They train shoulder-to-shoulder in markets that need the most help. They run Bootcamp workshops by DMA, focusing on an area coach and their restaurants per workshop.

**What the report gives them (4 tabs):**

| Tab | Feature | Why it matters |
|---|---|---|
| Overview | Goal Tracker | Shows if they're on pace for T1 reduction and T3 growth |
| Overview | Area & Franchisee Spotlight | Tells them **where to go** — lowest/highest areas and best/worst franchisee |
| Overview | Binding chart | Per-tier view of which component holds stores back |
| Overview | Default Watch | Quick check: any stores at risk of falling through the floor? |
| Portfolio | Drill-down (OA → DMA → Area → Store) | Before a workshop, drill into a DMA and see every store with scores, status, and trends |
| Portfolio | Store Detail | During a workshop, pull up a store's component scores |
| Boot Camps | Workshop History (date-aggregated) | Past and upcoming Boot Camp workshops by distinct date, with sparkline trends and per-store drill-down |
| Targeting | Bootcamp Targeting | **Where to go** — which area/franchisee has the most Tier 1 stores by count and concentration, with binding focus bars |

**The tier system they care about:**

```
< 2.5★  → Bootcamp  (needs intervention)
2.5–4.0 → Rising Star (target for promotion)
≥ 4.0   → Top Tier   (protect and replicate)
```

**The binding logic:** Whichever of the five components (Win Score, Speed, Brand, Hutbot, FSCC) has the lowest score determines what's holding the store back. That tells the OA what to coach on.

---

### 4. `rising_star.html` — Rising Star Targeting (Cross-Zone)

**Goal:** Identify the best DMA×Franchisee combinations for Rising Star workshops by aggregating Tier 2 stores nationally, independent of OA zone boundaries.

**Why a separate page:** A franchisee's stores within a single DMA may cross OA zone boundaries, but they should be targeted together. This page groups by DMA×Franchisee regardless of zone, so the right people are in the room.

**What the report gives them:**

| Tab | Feature | Why it matters |
|---|---|---|
| Targeting | National map of Tier 2 stores | Every Tier 2 store plotted with binding-constraint coloring — see the national distribution at a glance |
| Targeting | Top 30 DMA×Franchisee groups | Ranked by Tier 2 count with focus bars showing the dominant binding component — these are the best workshop targets |
| Targeting | Concentration rate | What % of this franchisee's stores in this DMA are Tier 2 (high rate = better ROI per workshop) |
| Targeting | Multi-zone flag | When a DMA×Franchisee group spans multiple OAs, flagged so scheduling gets the right coaches together |
| Workshops | Workshop History | Past and upcoming Rising Star workshops with per-store pre/post scores to measure lift |

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
