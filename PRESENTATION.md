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
          ├──► leadership_summary.html     (national health + watch list + workshop effectiveness)
          ├──► zone_scorecards.html        (per-OA deep dive + portfolio drill + workshop history)
          └──► fop_dashboard.html          (FOP/Director franchisee portfolio + per-FOP AI summaries)
```

**Why a Python script?** The CSV is ~34K rows and growing. Doing this in Excel would be error-prone and slow. Python automates the join, filter, aggregation, and HTML generation in ~30 seconds. Drop the file, run the script, get three reports.

**Why self-contained HTML?** No server, no database, no login. Each .html file embeds its own data as a JSON constant. Open it in any browser, share it as a file attachment, it just works.

---

## The Four Reports, Mapped to Roles

### 1. `zone_scorecards.html` — For OAs

**Goal:** Raise low-tier stores, promote top-tier stores.

**How OAs work:** They train shoulder-to-shoulder in markets that need the most help. They run Bootcamp workshops by DMA, focusing on an area coach and their restaurants per workshop.

**What the report gives them:**

| Feature | Why it matters |
|---|---|
| Overview tab → Goal Tracker | Shows if they're on pace for T1 reduction and T3 growth |
| Overview tab → Bootcamp Areas | Tells them **where to go** — which area/franchisee has the most Tier 1 stores, and what's binding them (Win Score? Speed? Brand?) |
| Portfolio tab (OA → DMA → Area → Store) | Lets them drill into a specific DMA before a workshop, see every store with scores, status, and trends |
| Store Detail | During a workshop, pull up a store's component scores and say "here's why you're in Bootcamp" |
| Default Watch | Quick check: any stores at risk of falling through the floor? |

**The tier system they care about:**

```
< 2.5★  → Bootcamp  (needs intervention)
2.5–4.0 → Rising Star (target for promotion)
≥ 4.0   → Top Tier   (protect and replicate)
```

**The binding logic:** Whichever of the five components (Win Score, Speed, Brand, Hutbot, FSCC) has the lowest score determines what's holding the store back. That tells the OA what to coach on.

---

### 2. `fop_dashboard.html` — For FOPs and Directors

**Goal:** Keep franchisees healthy and default-free.

**New:** Per-FOP AI summaries — when you select a FOP, an LLM-generated 3-paragraph insight (Past | Present | Future) appears at the top, summarizing franchisee shifts, risk distribution, and recommended actions.

**How FOPs work:** They manage the Franchisee relationship. If a franchisee's stores start defaulting, the FOP escalates with both the franchisee and the OA to build an action plan. They don't coach stores directly — they manage the portfolio.

**What the report gives them:**

| Feature | Why it matters |
|---|---|
| Director selector → FOP list | Director sees all FOPs under them, ranked by defaulting count |
| FOP selector → Franchisee table | FOP sees every franchisee, sorted by number of defaulting stores |
| Defaulting / At Risk / T1 Watch counts | At a glance: which franchisees need a phone call |
| Franchisee → Store list | Before a franchisee meeting, pull up every store in trouble |
| Store Detail → Status banner | Clear language: "Default threshold met — immediate improvement plan required" |

**The default framework:**

| Status | Criteria | Action |
|---|---|---|
| **Defaulting (dl)** | 3+ consecutive months < 2.0★ OR 4+ of last 5 | FOP escalates, OA builds plan |
| **At Risk (ar)** | 2 consecutive months < 2.0★ | Preventative intervention needed |
| **T1 Watch (tw)** | Latest score 2.0–2.5★ (Bootcamp but not default zone) | Monitor, address before it worsens |
| **OK** | Everything else | Business as usual |

**Why this matters:** A defaulting store isn't just a 5-Star problem — it's a Brand Standards failure. Per policy, repeated failures can affect franchise agreements. The FOP is the early warning system.

---

### 3. `leadership_summary.html` — For Leadership

**Goal:** Know the overall health of the system. Where are the problems? What are the problems? Is progress being made?

**What the report gives them:**

| Feature | Why it matters |
|---|---|
| Goal Tracker | T1 reduction, T3 growth, upward movement — is the system trending right? |
| Zone Ranking | Which zone is best/worst. Which director's territory needs attention. |
| Tier Movement (Sankey) | Are stores flowing up or down across the system? |
| National Trend (chart) | Are overall scores improving month over month? Which components are dragging? |
| Default Watch tab | Every store in trouble, sorted by severity, with OA and Franchisee — actionable to the individual level |
| Binding chart | What's holding each tier back nationally? If Bootcamp stores are all bound on Win Score, that's a strategic finding. |

**The leadership loop:**

```
Goal Tracker → shows if we're on pace
Zone Ranking → shows who needs help
Default Watch → shows who's in crisis
Trend       → shows if strategy is working
```

---

### 4. Workshop Effectiveness (in `leadership_summary.html`)

**Goal:** Measure whether Boot Camp workshops actually drive score improvement.

**What it shows:** Control vs. variable comparison — stores that attended a workshop vs. similar stores that didn't. Displayed as two side-by-side metric groups (n, avg benchmark, avg latest, avg improvement). A larger improvement in the workshop group validates the program.

---

## Key Design Decisions

**1. Why the threshold is 2.0★ for default, not 2.5★**
2.5★ is the Tier 1 boundary (Bootcamp). But per the Brand Standards Manual, < 2.0★ is a "Failure to Satisfy." Using 2.0★ for default detection aligns with policy, not just the tier system.

**2. Why consecutive months matter**
A store that scores 1.9★ in May is different from one that's been below 2.0★ since January. The consecutive count (`cu` in the data) distinguishes a bad month from a systemic problem.

**3. Why binding = lowest component**
A store's overall score is a weighted average. But the lowest component tells you what to fix. If Speed is the binding constraint, don't coach on Brand — coach on Speed. This is the actionable insight.

**4. Why three files instead of one**
Each role has a different entry point. Leadership doesn't care about DMA drill-down. OAs don't care about franchisee portfolios. Three files = three lenses, zero friction.

**5. Why the Store List is optional**
The Store List was originally required for Area/LatLong/FOP fields. Now the 5-Star CSV carries those columns directly, so the Store List join only overrides values when present. Simpler pipeline, fewer dependencies.

---

## Monthly Cadence

```
1st-5th: Scores close → export 5-Star.csv + Workshops.csv
5th:     python generate_reports.py
         → three HTML files ready
         → share links or attach files
```

No database, no server, no credentials (except optionally for LLM summaries). The reports are self-contained — email them, post them, open from a shared drive.

---

## The FSCC Gap (Elevated)

One known issue: the Brand Standards Manual says a failed FSCC should cap a store at 1.0★. The actual weighted-average formula lets FSCC be overridden by strong scores in other components. This means some stores with failing food safety scores appear in Tier 2 or 3. The reports reflect the formula as-calculated, not the policy override. **This is flagged for escalation — the reports are ready to implement an FSCC override as soon as policy alignment is decided.**
