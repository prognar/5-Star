# Remaining Issues — Franchisee Dashboard & Zone Scorecards

Status as of report period **Jan – Aug 2026** (files regenerated `2026-09-29`). All four items tracked below are **resolved**. Line numbers below refer to the current template files (`fz_dashboard.html`, `zone_scorecards.html`) and may shift after edits.

All metrics remain true Σ/Σ aggregations at every drill level.

---

## 1. Hide the LLM / AI summary box when drilling into a franchisee — DONE

**File:** `fz_dashboard.html` (fz only — zone uses inline "OA Insight" blocks that are replaced on navigation, no fix needed there).

**Fix:** `showFranchisee` now calls `showInsight(null, null)` before rendering the store list, matching `renderOverview`/`renderDirector`/`renderQuintiles`.

---

## 2. Metric-card trendlines must follow the Monthly / Quarterly / YTD toggle — DONE

**Files:** `fz_dashboard.html` and `zone_scorecards.html` (both have `metricPanel` + `_mSeries`).

**Fix:** `_mSeries(stores, m)` now branches on `_curView()`: Monthly → `[]` (no trendline), Quarterly → last 3 months (`all.slice(MONTHS.length - 3)`), YTD → all months. `sparkline([])` already returned `''`, so the empty-monthly case renders cleanly and the value/sparkline visibility filter (`_mNow(...)!=null || _mSeries(...).some(...)`) still works.

---

## 3. 5-Star exported cards: show the Score **and** the Value (except Brand and FSCC) — DONE

**Files:** `fz_dashboard.html` (`fzCardHTML` component grid, store-detail comp-grid), `zone_scorecards.html` (`zoneCardHTML`, store-detail comp-grid).

**Fix:** Added a `CK_TO_NS = {cw:'WIN', cs:'SPEED', ch:'HB'}` map in each component-grid renderer. For Win Score / Speed / Hutbot cards, the raw value (`s.ns.<K>.a`, e.g. `64.3%`) now renders next to the 0–5 score. Brand (`cb`) and FSCC (`cf`) keep the 0–5 score only, since they have no `ns` entry.

---

## 4. Exported files must state the report timeframe — DONE

**Files:** `fz_dashboard.html` (`fzCardHTML`), `zone_scorecards.html` (`zoneCardHTML`), plus `generate_reports.py`.

**Fix:**
- Added a `REPORT_YEAR` global in `generate_reports.py` (set alongside `MONTH_LABELS`/`PERIOD_MONTHS` in `filter_analysis_data`), injected into both templates via a `const REPORT_YEAR = 2026;` line placed right after `const MONTHS = [...]`, replaced at generation time with a regex swap in `generate_zones_html`/`generate_fop_html`.
- Added a shared `_periodLabel()` helper in both templates: Monthly → the month (e.g. **Aug 2026**), Quarterly → the range (e.g. **Jun – Aug 2026**), YTD → the full range (e.g. **Jan – Aug 2026**).
- Card header label and footer in `fzCardHTML`/`zoneCardHTML` now use `_periodLabel()` instead of the generic `Monthly/Quarterly/YTD` string; the footer keeps a `generated <date>` stamp instead of the old full runtime clock.

---

## Verification hooks (apply after any fix)

```powershell
python generate_reports.py --run-date 2026-09-15
python .\scripts\_verify_five.py     # expect OVERALL: PASS (esprima-clean)
```

Sanity: headless Edge load of `fz_dashboard.html` (dump-dom, `--virtual-time-budget=90000`).

Confirmed via `python scripts/_verify_five.py` → `OVERALL: PASS` after regenerating all five HTML outputs with these fixes in place.
