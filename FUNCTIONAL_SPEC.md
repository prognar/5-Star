# 5-Star Reporting Suite — Functional Spec

## What this is

The 5-Star program scores every Pizza Hut franchise restaurant each month across five
operational components (Win Score, Speed, Brand, Hutbot On-Time, FSCC), blended into one
overall star rating. That raw monthly data, on its own, doesn't tell any one role what to do
next. This suite turns it into five purpose-built, self-contained HTML reports — one dataset,
five lenses — so Leadership, Directors, FOPs, OAs, and Training all get the view that answers
their specific questions, without needing a database, a login, or a BI tool. Each file is a
single HTML page you open in a browser or share as an attachment.

**The core idea driving every design choice:** a store's overall score is a weighted average,
but the *lowest* of its five components — its "binding constraint" — is what actually tells
someone what to coach on. Every report surfaces binding constraints, not just overall scores,
because that's the actionable layer.

## The five reports

| Report | Audience | One-line purpose |
|---|---|---|
| `leadership_summary.html` | Leadership, Directors, Strategy | National health in one page: zone ranking, tier movement, binding breakdown, workshop ROI, default watch list |
| `fz_dashboard.html` (Franchisee Dashboard) | FOPs, Directors | Franchisee-portfolio health, drill-down Director → FOP → Franchisee → Store, default/at-risk tracking |
| `zone_scorecards.html` | OAs | Per-zone deep dive: goal tracking, DMA/Area drill-down, Boot Camp history, where to target workshops next |
| `rising_star.html` | OAs, Directors, Leadership | Cross-zone Tier 2 (Rising Star) targeting by DMA×Franchisee, independent of zone boundaries |
| `leadership_brief.html` | Leadership (private, not linked from the others) | One-page executive pulse: recognition, Boot Camp ROI, franchisees on the rise/to watch |

All five are generated together by one script (`generate_reports.py`) from the same underlying
data, so a number means the same thing wherever you see it across reports.

## The tier and status vocabulary everyone shares

**Tiers** (based on a store's monthly — or, for coverage purposes, trailing 3-month — overall
5-Star score):

| Tier | Name | Range | Meaning |
|---|---|---|---|
| 1 | Bootcamp | < 2.5★ | Needs intervention |
| 2 | Rising Star | 2.5★ – 4.0★ | On track, room to grow |
| 3 | Top Tier | ≥ 4.0★ | Excellent — protect and replicate |

**Store status** (independent of tier, tied to the Brand Standards Manual's default language —
see Technical Spec for the exact rule):

| Status | Plain meaning | Who acts |
|---|---|---|
| **Defaulting** | Has crossed the contractual default threshold | FOP escalates, formal improvement plan |
| **At Risk** | One step from defaulting | FOP/OA preventative intervention |
| **T1 Watch** | In Bootcamp tier but not yet in trouble | Monitor, get ahead of it |
| **OK** | Everything else | Business as usual |

**Binding constraint:** whichever of the five components (Win Score, Speed, Brand, Hutbot,
FSCC) is a store's lowest score. If a tier's stores are mostly bound on Speed, that's where
coaching time goes — not Brand, not Win Score.

## Boot Camp & Rising Star workshops

OAs run **Boot Camp** workshops for Tier 1 stores and **Rising Star** workshops for Tier 2
stores, shoulder-to-shoulder, usually grouped by DMA and Area Coach. Every report that touches
workshops measures the same thing: did the stores that attended improve more than similar
stores that didn't? That comparison (control vs. attendees, tier-matched) is the **Workshop
Effectiveness** analysis that appears in Leadership Summary and Zone Scorecards.

A workshop's value is tracked through four checkpoints: a pre-workshop **baseline**, then
**30/60/90-day** follow-ups. A store only counts toward "measurable" once it has reached the
30-day mark — before that, it's counted as "had a Boot Camp" but not yet averaged into
improvement stats, so early attendees can't quietly drag down the numbers before they've had
time to show results.

## How each role uses the suite

### Leadership — `leadership_summary.html` and `leadership_brief.html`

Leadership sets strategy: which zones need investment, whether training is paying off, where
to escalate. They don't need store-level detail — they need trends, risk concentration, and a
narrative they can walk into a meeting with.

- **National Insight** — a one-paragraph read of what happened, where things stand, and the
  top priority (AI-written when available, otherwise a data-driven fallback — there's always
  content).
- **Zone Ranking** — every zone sorted by current average, with trend severity shown through
  color (darker = more severe move, green = improving, red = declining).
- **Tier Movement (Sankey)** — are stores flowing up or down across the whole system?
- **Binding chart** — nationally, which component is holding each tier back.
- **Default Watch** — every defaulting / at-risk / T1-watch store nationwide, sorted by
  severity, with OA and Franchisee attached.
- **Workshop Effectiveness** — did Boot Camp / Rising Star investment actually move the needle?
- **`leadership_brief.html`** is the private, recognition-focused companion: who had the
  standout month, Boot Camp pulse, franchisees on the rise vs. to watch. Not linked from the
  shared pages — open it directly.

### Director — `fz_dashboard.html`

A Director selects their name from the dropdown and gets their whole territory rolled up:
every FOP under them, every franchisee under those FOPs, sorted by default risk. The headline
score updates to their territory's store-weighted average. From there they drill into a FOP, a
franchisee, or an individual store exactly like a FOP would.

### FOP (Franchise Operations Partner) — `fz_dashboard.html`

FOPs manage the franchisee relationship — not individual stores. Their job is to know, before a
franchisee call, which stores are in trouble and why.

- Select their name (or land on "All" for the full cross-portfolio view) to see every
  franchisee they manage, sorted by defaulting-store count.
- Get an AI-written 3-paragraph summary (Past | Present | Future) per FOP — portfolio shifts,
  risk distribution, recommended action.
- Click into a franchisee for the full store list: status badges, trend arrows, search, and
  Region/Area-Coach filters.
- Click a store for the full component breakdown and a plain-language status banner (e.g.
  "Default threshold met — immediate improvement plan required").
- The **Alignment tab** is a separate, flat, filterable list of every open store with its full
  org-hierarchy assignment (OA/Zone/FOP/Director/DMA/Region/Area/address/lat-long) — useful for
  "who owns this store" lookups independent of the drill-down above.
- The **LM / LQ / YTD** toggle changes the scoring window everywhere at once (headline, cards,
  tables) — YTD is the default; LQ is a rolling 3-month average.

### OA (Operations Assistant / Zone Manager) — `zone_scorecards.html` and `rising_star.html`

OAs train shoulder-to-shoulder in the markets that need the most help and run the Boot Camp /
Rising Star workshops.

- **Goal Tracker** — progress toward the annual Tier 1 reduction (−50%) and Tier 3 growth
  (+50%) targets, plus gross stores moved up, moved down, stayed, and closed since January.
- **Tier 1 Boot Camp Coverage** — of the stores currently in Tier 1 (trailing 3-month average),
  what fraction have had, or have scheduled, a Boot Camp? Shown as a donut (Had / Scheduled /
  Need) next to the Goal Tracker cards, with a worklist below for new Tier 1 entrants since
  January that haven't been reached yet.
- **Area & Franchisee Spotlight** — where to go next: lowest/highest areas, best/worst
  franchisee.
- **Binding chart** — what's holding each tier back in this zone specifically.
- **Portfolio drill-down** — OA → DMA → Area → Store → Component, for prepping a specific visit.
- **Boot Camps tab** — past workshop history (baseline, post-scores, deltas, sparkline) and
  upcoming/scheduled workshops.
- **Targeting tab** — Tier 1 stores ranked by area, to decide where the next Boot Camp should
  go.
- **`rising_star.html`** does the same targeting job for Tier 2 stores, but zone-agnostic — a
  franchisee's footprint in a DMA can cross OA boundaries, so this page groups by DMA×Franchisee
  instead of by zone, to get the right people in the room.

### Training — Boot Camp / Rising Star program owners

Training's lens is the **Workshop Effectiveness** sections (Leadership Summary, Zone
Scorecards) and the **Tier 1 Boot Camp Coverage** card (Zone Scorecards): did the program
measurably move scores for stores that attended vs. a tier-matched control group that didn't,
and is coverage of the target population (Tier 1 stores) keeping pace with the goal of reaching
all of them? The "Had Boot Camp" vs. "Measurable (30+ days)" split in every Boot Camp
Effectiveness table separates "we've reached this store" from "we can already see the result."

## Monthly cadence

```
Scores close (1st–5th of month)
        │
        ▼
python generate_reports.py --run-date <today>
        │  (pulls live from Snowflake; falls back to manual CSVs if unreachable)
        ▼
5 HTML files regenerated in place, ~30 seconds
        │
        ▼
push_to_prod.sh "<commit message>"   → publishes to the team GitHub repo
```

No database, no server, no login for end users — every report is a single file. Share it as an
attachment, a link, or open it from a shared drive.

## Known open item

**FSCC weighted-average gap.** The Brand Standards Manual says a failed food-safety (FSCC)
score should cap a store at 1★ for that period. The actual formula blends FSCC at only ~7.5%
of the overall score, so a store can fail FSCC outright and still land in Tier 2 or 3 if its
other four components are strong. The reports currently reflect the formula as calculated, not
the policy override — this is flagged for a leadership decision (add a post-blend FSCC cap, or
update the policy language to match the formula), not something the reporting suite should
silently decide on its own.
