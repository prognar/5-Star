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
- **Rising Star targeting**: unaffected by default classification

---

## FSCC Weighted-Average Gap — Recommendation

**Issue:** The Brand Standards Manual states that any store that fails food safety (FSCC) should be capped at 1-star (Tier 1) for that period. However, the current 5-star formula uses a weighted average of all five components, where FSCC contributes only **~7.5%** of the blend.

**Concrete example:** A store could score **0.0 on FSCC** but still land in **Tier 2 or even Tier 3** if its other four components (Win Score, Speed, Brand, Hutbot) are strong enough to pull the weighted average above 2.5.

**Current reports** match the weighted-average formula exactly — they reflect the data as calculated, not the policy override.

**Recommendation to take up the chain:**

> *Option A — Policy alignment:* Add a post-blend override step: if FSCC_STAR < threshold (e.g. < 2.5), cap OVERALL_FIVESTAR at 1.0 for that period, regardless of other component scores.
>
> *Option B — Policy update:* If the weighted-average formula is intentional, update the Brand Standards Manual to remove or clarify the 1-star cap language so that field expectations match the actual calculation.
