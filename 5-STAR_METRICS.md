# 5-Star Metric Dictionary — Master Reference

Source file: `5-Star full.csv` (76 columns, monthly snapshot per store).
Domain: Pizza Hut US stores, monthly. Store concept can be delivery or non-delivery.

## The One Aggregation Rule

> **Never average the averages — sum the parts, then calculate.**

Every metric below is a *ratio* (percentage or average). For a **single store** it is computed
directly from that store's rows. When rolling up **more than one store** (Area, Franchisee, DMA,
Region, Zone, National, or any group):

1. Sum the **numerator** across all member stores.
2. Sum the **denominator** across all member stores.
3. Divide the summed numerator by the summed denominator.

This applies to every metric marked **Σ/Σ** in the tables below. The only exceptions are:

- **WAVG (scorecard scores/stars)** — per-store ratings that are not built from raw counts
  (audits, surveys): weight each store's value by its volume and average.
- **AVG (periodic counters)** — per-snapshot counters (web deactivations, RGM % on-duty
  spans): plain average across stores.
- **SUM (volume-style metrics)** — total hours/counts: plain sum.

Example — "Del < 30 %" for a DMA: roll up as `Σ(DEL_LESS_30) / Σ(TOT_DEL_BTN_5_120_CNT)`,
**never** `avg(DEL_LESS_30 / TOT_DEL_BTN_5_120_CNT)`.

`POLL_COUNT` is poll *days* in the month (23–31): to get a weekly rate, `Σ value / Σ polls × 7`.

Legend — Scope: **D** = delivery only, **N** = non-delivery only, **D/N** = branched by concept, **A** = all.
Non-delivery site types: `RBD`, `COO`, `RR`, `TRA`, `RED ROOF`.

---

## 1. Scorecard outputs (5-Star & components)

5-Star is the monthly store performance scorecard measuring restaurant health across five core
operational components; the store's overall star is the weighted sum of component stars.
Weights: Win 0.35 · Speed 0.30 · Hutbot On Time 0.20 · Brand 0.075 · FSCC 0.075.

| Standard name | Source field(s) | Definition | Store-level formula | Scope | Roll-up |
|---|---|---|---|---|---|
| Avg Five Star | `OVERALL_FIVESTAR` | Monthly overall store performance star (1–5), weighted across the five components below. | N/A (provided) | A | WAVG |
| Win Score | `WIN_SCORE_ACTUAL`, `WIN_SCORE_STAR` | Customer satisfaction & guest experience — Surveys, Aggregator ratings (DoorDash, Uber Eats, GrubHub, etc.), and Reviews (Google, Yelp, etc.). | % provided; star mapped off thresholds | A | WAVG |
| Speed | `SPEED_ACTUAL`, `SPEED_STAR` | Out-the-door / production speed. Delivery = OTD under 18 min. Non-delivery = production time under 15 min. | D: OTD < 18 % · N: PROD < 15 % | D/N | Σ/Σ (recompute % from parts) |
| FSCC | `FSCC_ACTUAL`, `FSCC_STAR` | Food safety performance & compliance. | % provided; star mapped | A | WAVG |
| Brand | `BRAND_ACTUAL`, `BRAND_STAR` | Adherence to Pizza Hut brand standards. | % provided; star mapped | A | WAVG |
| Hutbot On Time | `HB_ONTIME_ACTUAL`, `HB_ONTIME_STAR` | Execution of required routines on time — % of routines completed on time. | % provided; star mapped | A | WAVG |

Star thresholds (locked, confirmed 2026-10): each metric's monthly % is graded 1-5 at these cutoffs
(1 = below the first value, 5 = at/above the last):

| Metric | 1★ | 2★ | 3★ | 4★ | 5★ |
|---|---|---|---|---|---|
| Win Score | <49% | 49–60% | 60–66% | 66–71% | ≥71% |
| Speed | <40% | 40–60% | 60–70% | 70–80% | ≥80% |
| Hutbot On Time | <80% | 80–85% | 85–90% | 90–95% | ≥95% |

As arrays: Win `[49, 60, 66, 71]`, Speed `[40, 60, 70, 80]`, HB `[80, 85, 90, 95]`.
Defined in `generate_reports.py` (`STAR_THRESHOLDS`) and mirrored in `fz_dashboard.html`
(`PCT_BAND_THRESHOLDS`) for the Franchisee Dashboard's % Actual toggle — keep both in sync.

## 2. Customer / survey scores

| Standard name | Source field(s) | Definition | Store-level formula | Scope | Roll-up |
|---|---|---|---|---|---|
| Taste Score | `TASTE_SCORE` | How customers feel about the store's taste. | 0–100 provided | A | AVG |
| Accuracy Score | `ACCURACY_SCORE` | How customers feel about the store's accuracy. | 0–100 provided | A | AVG |
| Speed Score | `SPEED_SCORE` | How customers feel about the store's speed. | 0–100 provided | A | AVG |
| OSAT Score | `OSAT_SCORE` | How customers feel about the store overall — less is better (reverse-graded). | 0–100 provided, track reversed | A | AVG |

## 3. Operational ratios — delivery only (**D**, all Σ/Σ)

> **DaaS dependency caveat:** when DaaS share is high, rack time (and OTD) is partly
> controlled by 3rd-party (DoorDash) driver *arrival* timing, not the store. Interpretation:
> - Rack time ≥ 8 min **and** DaaS share ≥ 50% → orders wait on DaaS pickup; not an internal
>   driver-hours issue, treat rack time as informational.
> - Rack time ≥ 8 min **and** DaaS share < 50% → internal dispatch / driver-utilization problem;
>   fixable (tighten dispatch windows, batch runs by due time) or lean into DaaS.

| Standard name | Source field(s) | Definition | Store-level formula |
|---|---|---|---|
| Del > 45 % | `DEL_GRT_45`, `TOT_DEL_BTN_5_120_CNT` | % of deliveries taking longer than 45 minutes. | `DEL_GRT_45 / TOT_DEL_BTN_5_120_CNT` |
| Del < 30 % | `DEL_LESS_30`, `TOT_DEL_BTN_5_120_CNT` | % of deliveries completed under 30 minutes. | `DEL_LESS_30 / TOT_DEL_BTN_5_120_CNT` |
| Promise time ± 10 % | `PROMISE_TIME_WITHIN_10`, `DEL_TIME_CNT` | % of deliveries within 10 minutes of the promise-time window. | `PROMISE_TIME_WITHIN_10 / DEL_TIME_CNT` |
| Del Time (avg) | `DEL_TIME`, `DEL_TIME_CNT` | Average delivery time (out the door to delivered). | `DEL_TIME / DEL_TIME_CNT` |
| OTD Time (avg) | `SUM_OUT_THE_DOOR_TIME`, `TOT_DEL_OUT_THE_DOOR_TIME_CNT` | Avg out-the-door time — production + rack time. | `SUM_OUT_THE_DOOR_TIME / TOT_DEL_OUT_THE_DOOR_TIME_CNT` |
| OTD < 18 % | `OUT_THE_DOOR_TIME_LT_18_CNT`, `TOT_DEL_OUT_THE_DOOR_TIME_CNT` | % of orders out the door under 18 minutes. | `OUT_THE_DOOR_TIME_LT_18_CNT / TOT_DEL_OUT_THE_DOOR_TIME_CNT` |
| Avg Rack Time | `DEL_RACK_TIME`, `DEL_RACK_TIME_CNT` | Avg time an order sits on the rack completed (internal or DaaS driver not yet picked up). | `DEL_RACK_TIME / DEL_RACK_TIME_CNT` |
| Drive Time (avg) | `DRIVE_TIME`, `TOT_DEL_DRIVE_TIME_CNT` | Average drive time. | `DRIVE_TIME / TOT_DEL_DRIVE_TIME_CNT` |
| DaaS % | `DAAS_DELIVERIES`, `INTERNAL_DELIVERIES` | % of orders delivered by Delivery-as-a-Service drivers (non-Pizza Hut staff; we wait for arrival). | `DAAS_DELIVERIES / (DAAS_DELIVERIES + INTERNAL_DELIVERIES)` |

## 4. Operational ratios — non-delivery only (**N**, all Σ/Σ)

| Standard name | Source field(s) | Definition | Store-level formula |
|---|---|---|---|
| Avg Rack Time (non-del) | `NON_DEL_RACK_TIME`, `NON_DEL_RACK_TIME_CNT` | Avg rack time for non-delivery stores. | `NON_DEL_RACK_TIME / NON_DEL_RACK_TIME_CNT` |

## 5. Operational ratios — branched by concept (**D/N**, all Σ/Σ)

For each metric the applicable branch is picked per store concept; at roll-up sum parts **within each branch** before dividing.

| Standard name | Source field(s) | Definition | Store-level (delivery) | Store-level (non-delivery) |
|---|---|---|---|---|
| Avg Make Time | `MAKE_TIME`, `NON_DEL_MAKE_TIME`, `TOT_DEL_BTN_5_120_CNT`, `TOT_NON_DEL_CNT` | Time from order in to order into the oven. | `MAKE_TIME / TOT_DEL_BTN_5_120_CNT` | `NON_DEL_MAKE_TIME / TOT_NON_DEL_CNT` |
| Make < 4 % | `MAKE_LESS_4`, `NON_DEL_MAKE_TIME_LT_4_CNT`, `TOT_DEL_BTN_5_120_CNT`, `TOT_NON_DEL_CNT` | % of orders into the oven in under 4 minutes. | `MAKE_LESS_4 / TOT_DEL_BTN_5_120_CNT` | `NON_DEL_MAKE_TIME_LT_4_CNT / TOT_NON_DEL_CNT` |
| Prod Time (avg) | `PROD_TIME`, `NON_DEL_PROD_TIME`, `PROD_TIME_CNT`, `TOT_NON_DEL_PROD_TIME_CNT` | Avg production time — order in to on the rack (make + oven). | `PROD_TIME / PROD_TIME_CNT` | `NON_DEL_PROD_TIME / TOT_NON_DEL_PROD_TIME_CNT` |
| Prod < 15 % | `PROD_LESS_15`, `NON_DEL_PROD_LESS_15`, `TOT_DEL_BTN_5_120_CNT`, `TOT_NON_DEL_PROD_TIME_CNT` | % of orders with production time under 15 minutes. | `PROD_LESS_15 / TOT_DEL_BTN_5_120_CNT` | `NON_DEL_PROD_LESS_15 / TOT_NON_DEL_PROD_TIME_CNT` |

Note: `TOT_DEL_BTN_5_120_CNT` (orders between 5 and 120 minutes) is the outlier-windowed denominator
for delivery-side serve-time percentages; it is **not** `TOT_DEL_CNT`.

## 6. Sales & business metrics (all Σ/Σ — sum sales/trans, then compute)

| Standard name | Source field(s) | Definition | Store-level formula |
|---|---|---|---|
| WPRA | `CY_TOTAL_NET_SALES`, `POLL_COUNT` | Weekly Per Restaurant Average — avg weekly sales. | `CY_TOTAL_NET_SALES / POLL_COUNT × 7` |
| Weekly Traffic | `DIGITAL_ORDERSOURCE`, `NON_DIGITAL_ORDERSOURCE`, `POLL_COUNT` | Average orders per week. | `(DIGITAL_ORDERSOURCE + NON_DIGITAL_ORDERSOURCE) / POLL_COUNT × 7` |
| AGC | `CY_TOTAL_NET_SALES`, `CY_SS_TRANS` | Average Guest Check. | `CY_TOTAL_NET_SALES / CY_SS_TRANS` |
| SSSG | `CY_SS_SALES_TNS`, `LY_SS_SALES_TNS` | Same Store Sales Growth — this month vs same month last year. | `(CY_SS_SALES_TNS − LY_SS_SALES_TNS) / LY_SS_SALES_TNS` |
| SSTG | `CY_SS_TRANS`, `LY_SS_TRANS` | Same Store Transactions Growth — this month vs same month last year. | `(CY_SS_TRANS − LY_SS_TRANS) / LY_SS_TRANS` |
| Cancels Made % | `CANCELS_MADE_AMT`, `CY_TOTAL_NET_SALES` | % of orders canceled where materials were used, of sales. | `CANCELS_MADE_AMT / CY_TOTAL_NET_SALES` |
| Cancels Not Made % | `CANCELS_NOTMADE_AMT`, `CY_TOTAL_NET_SALES` | % of orders canceled before materials were used, of sales. | `CANCELS_NOTMADE_AMT / CY_TOTAL_NET_SALES` |

## 7. Hours & availability (store-level product; roll-up = **SUM** of store values)

| Standard name | Source field(s) | Definition | Store-level formula |
|---|---|---|---|
| Weekly CO Hours | `AVAIL_CO_HOURS`, `POLL_COUNT` | Weekly average of Carry Out hours open. | `AVAIL_CO_HOURS * POLL_COUNT * 7` |
| Weekly Del Hours | `AVAIL_DEL_HOURS`, `POLL_COUNT` | Weekly average of Delivery hours open. | `AVAIL_DEL_HOURS * POLL_COUNT * 7` |
| Web Deactivations | `WEB_DEACTIVATIONS` | Avg number of times web ordering was turned off this month. | provided (counter) |
| Product Outages | `PRODUCT_OUTAGES` | Number of product outages this month. | provided (counter) |
| RGM % | `RGM_FLG`, `POLL_COUNT` | % of the month a Restaurant GM was on duty; gaps from turnover — <100% not ideal. | `RGM_FLG / POLL_COUNT × 100` |

Roll-up for these = **AVG** (web deactivations / outages) or **SUM** of the store-level
hour products (weekly hours are already rates — a group's weekly hours = Σ store hours),
or **Σ/Σ** (RGM % — sum on-duty days over sum days polled, then divide).

## 8. Raw fields — "the parts" (never averaged directly)

These are the building blocks used by the Σ/Σ aggregates above. When rolling up a group, sum
these across stores *first*, then form the ratio.

| Field | Meaning |
|---|---|
| `PROD_TIME` / `PROD_TIME_CNT` | Total production time / # orders counted in production time |
| `DEL_TIME` / `DEL_TIME_CNT` | Total delivery time / # orders counted in delivery time |
| `MAKE_TIME` | Total make time |
| `DEL_RACK_TIME` / `DEL_RACK_TIME_CNT` | Total rack time (deliveries) / # orders counted in rack time |
| `TOT_DEL_CNT` | Total number of deliveries |
| `DEL_LESS_30` | Orders delivered under 30 minutes |
| `DEL_GRT_45` | Orders delivered over 45 minutes |
| `PROMISE_TIME_WITHIN_10` | Orders within 10 min of promise-time window |
| `MAKE_LESS_4` | Orders with make time < 4 minutes |
| `PROD_LESS_15` | Orders with production time < 15 minutes |
| `NON_DEL_RACK_TIME` / `NON_DEL_RACK_TIME_CNT` | Total rack time (non-delivery) / # orders with a rack time |
| `NON_DEL_PROD_TIME` / `NON_DEL_PROD_LESS_15` | Total production time (non-delivery) / # orders < 15 min |
| `NON_DEL_MAKE_TIME` / `NON_DEL_MAKE_TIME_LT_4_CNT` | Total make time (non-delivery) / # orders make < 4 min |
| `TOT_NON_DEL_CNT` | # orders at non-delivery stores |
| `TOT_NON_DEL_PROD_TIME_CNT` | # orders with a production time (non-delivery) |
| `SUM_OUT_THE_DOOR_TIME` / `TOT_DEL_OUT_THE_DOOR_TIME_CNT` | Total OTD time / # OTD orders (delivery) |
| `OUT_THE_DOOR_TIME_LT_18_CNT` | Orders OTD under 18 minutes |
| `DRIVE_TIME` / `TOT_DEL_DRIVE_TIME_CNT` | Total drive time / # orders with a drive time |
| `TOT_DEL_BTN_5_120_CNT` | # delivery orders between 5 and 120 minutes (outliers thrown out — **the** delivery denominator) |
| `ORD_MARKED_DEL_ON_RETURN` | ⚠ definition pending (field present, no formula assigned yet) |
| `DAAS_DELIVERIES` / `INTERNAL_DELIVERIES` | DaaS deliveries / Pizza Hut driver deliveries |
| `CANCELS_MADE_AMT` / `CANCELS_NOTMADE_AMT` | $ value of cancels with / without materials used |
| `AVAIL_CO_HOURS` / `AVAIL_DEL_HOURS` / `POLL_COUNT` | Carry-Out / Delivery hours open across N polls in month |
| `WEB_DEACTIVATIONS` / `PRODUCT_OUTAGES` | Web-ordering off events / product outages (all zero in current data) |
| `DIGITAL_ORDERSOURCE` / `NON_DIGITAL_ORDERSOURCE` | Order counts by channel (online / not online) |
| `RGM_FLG` | Days a Restaurant GM was on duty per month (1–31, polled) |
| `CY_TOTAL_NET_SALES` / `CY_SS_SALES_TNS` / `LY_SS_SALES_TNS` | Net sales / same-store sales CY / LY |
| `CY_SS_TRANS` / `LY_SS_TRANS` | Same-store transactions CY / LY |

## Pending fields

- `ORD_MARKED_DEL_ON_RETURN` — present in the CSV; definition not yet assigned to any metric (carried but unused).
- `DaaS %` and **Weekly Traffic** depend on `DAAS_DELIVERIES` / `INTERNAL_DELIVERIES` and
  `DIGITAL_ORDERSOURCE` / `NON_DIGITAL_ORDERSOURCE` — all now present in the CSV (verified present;
  values unverified).