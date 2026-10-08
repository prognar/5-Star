# 5-Star Reporting Suite — Technical Spec

For *what* this suite does and *who* uses it, see `FUNCTIONAL_SPEC.md`. This document is the
"how it actually works" reference: where the data comes from, what the generator does with it,
every formula, and the moving parts a new developer (or a fresh Claude session) needs to know
before touching `generate_reports.py`.

## 1. Architecture at a glance

```
Snowflake (live)  ──┐
                     ├──► generate_reports.py ──► 5 self-contained HTML files
Manual CSVs (fallback)┘         (one script)         + 1 companion JS data file
```

- **One Python script** (`generate_reports.py`) does everything: pull data, compute every
  metric/tier/status, write all 5 HTML reports. No build step, no server, no database at
  runtime.
- **Each HTML report is self-templating.** `generate_reports.py` reads its own previous output
  (`template_dir == OUTPUT_DIR == BASE_DIR`) as the template for the next run, and only
  replaces specific `const NAME = JSON.parse("...")` data blocks via `replace_data_block()`.
  Everything else — markup, CSS, JS logic, UI features — is edited by hand directly in the
  `.html` files and survives every regeneration untouched. **This means: if you're adding a UI
  feature (a new chart, a new filter, a new card), edit the `.html` file directly — you do not
  need to touch the Python generator unless the feature needs new *data* fields.**
- Runs in ~30 seconds end to end, including live Snowflake pulls.

## 2. Data sources

### Primary path: live Snowflake (PAT / REST API, no browser)

As of 2026-10, nothing needs to be exported by hand. `generate_reports.py` tries Snowflake
first, every run, for both of its two main pulls:

| Function | Pulls | Backing query | Falls back to |
|---|---|---|---|
| `load_5star_from_snowflake()` | Store-month 5-Star facts | `FIVESTAR_SQL` against `AXC1195.FXT_DASHBOARD_BASE_MONTHLY` | `5-Star full.csv` |
| `load_alignment_from_snowflake()` | Org-hierarchy (OA/Zone/FOP/Director/DMA/Area) for the Alignment tab | `ALIGNMENT_SQL` against `DSC.ALIGN_DIM_V1` (joined to zone/FOP/director override tables) | `Alignment.csv` |

Both SQL strings live as module-level constants in `generate_reports.py` (`FIVESTAR_SQL`,
`ALIGNMENT_SQL`) — edit them there, not in this doc, so code and docs can't drift apart.

**Auth — preferred: Programmatic Access Token (PAT) over the SQL REST API.**
This is the mechanism to use; it never opens a browser and never times out waiting on SSO.

- The token lives encrypted at `%LOCALAPPDATA%\snowflake\pat.txt`, protected with Windows DPAPI
  (tied to this Windows user + this machine). It's set up and managed by tooling at
  `C:\projects\snowflake\` (shared with other Snowflake scripts on this machine, not specific
  to this repo).
- **One-time setup / rotation:** generate a PAT in Snowflake under role `PH_USER_EW` (or
  whatever role you're granted), then run `C:\projects\snowflake\store_pat.ps1` and paste it
  when prompted. Verify with `powershell -ExecutionPolicy Bypass -File snow.ps1 smoke_test.py`
  in that same folder.
- `generate_reports.py`'s `_get_snowflake_pat()` decrypts it via a short PowerShell
  `ConvertTo-SecureString` / `SecureStringToBSTR` one-liner (mirrors `snow.ps1`'s own decrypt
  logic exactly), caches it in-process for the run, and `_snowflake_pat_query_df()` POSTs the
  query to `https://{account}.snowflakecomputing.com/api/v2/statements` with
  `Authorization: Bearer <pat>` and `X-Snowflake-Authorization-Token-Type:
  PROGRAMMATIC_ACCESS_TOKEN`, polling until the statement completes and stitching together any
  multi-partition result.
- Relevant env vars (set in `.env`): `SNOWFLAKE_ROLE` (default `PH_USER_DATASCIENCE`),
  `SNOWFLAKE_DATABASE` (`DATASCIENCE`), `SNOWFLAKE_WAREHOUSE` (`PROD_ANALYTIC_WH`),
  `SNOWFLAKE_SCHEMA`. The account defaults to `lj10919.us-east-1` if `SNOWFLAKE_ACCOUNT` isn't
  set.
- Param substitution into SQL uses a targeted `.replace(f"%({k})s", f"'{v}'")`, **not** blind
  `sql % params` — `ALIGNMENT_SQL` contains a literal `LIKE 'PIZZA HUT%'` wildcard that a plain
  `%`-format would choke on.

**Fallback path (if no PAT): `connections.toml` / external-browser SSO.**
If `SNOWFLAKE_CONNECTION_NAME` is set (reusing a profile from `~/.snowflake/connections.toml`,
whatever `snow sql` already uses on this machine) or the explicit
`SNOWFLAKE_ACCOUNT`/`SNOWFLAKE_USER`/`SNOWFLAKE_PASSWORD` env vars are set, the script falls
back to the `snowflake.connector` package. This path *can* pop a browser SSO prompt
(`client_store_temporary_credential=True` caches the session afterward, but the very first
connection after it expires will still prompt) — this is why the PAT path is strongly
preferred for unattended/scheduled runs. Both connection attempts are capped with
`login_timeout` (15s / 60s) so a run can never hang indefinitely waiting on an interactive
prompt.

**Last-resort fallback: manual CSV.** If Snowflake is unreachable through either path, the
script reads `5-Star full.csv` / `Alignment.csv` from disk unchanged, exactly like the original
manual-export workflow. Nothing breaks if Snowflake is down — you just lose freshness, not
functionality.

**`Workshops.csv` is the one remaining manual export** (Boot Camp / Rising Star attendance —
query in the "Exporting Data" section below). It is **not** committed to the public GitHub
repo (real store/franchisee attendance data) — see §7.

### Pulling closed-store status

`FIVESTAR_SQL`'s source view (`AXC1195.FXT_DASHBOARD_BASE_MONTHLY`) carries a `STATUSDESC`
column, but it reflects each store's **current** status, not its status as-of that historical
month — the same value is repeated across every row for a store, open or closed. This matters
a lot: `filter_analysis_data()` filters every row to `STATUSDESC == 'Open'` (see §4), which
means a store that has since closed gets its **entire** history excluded, including its
January baseline row — not just its post-closure months. A naive "present in January, missing
in the latest month" diff against the filtered data can never detect a closure, because the
closed store was never in the filtered data at all, in any month.

The fix: `filter_analysis_data()` captures closures from the **raw, unfiltered** dataframe,
*before* applying the `STATUSDESC == 'Open'` mask — any store with a real January score
(`OVERALL_FIVESTAR` not null) whose current `STATUSDESC != 'Open'` goes into the module-level
`CLOSED_SINCE_JAN` list, carrying store id, status, franchisee, OA, FOP, Director, and Area. The
source view sometimes leaves `OPX_FOP`/`OPX_DIRECTOR`/`FAREADESC` blank specifically for closed
stores (those org-hierarchy fields look like they're derived from a current-roster join
upstream), so these are backfilled from the same franchisee's still-open stores — confirmed
every franchisee maps to exactly one FOP/Director among open stores, so this is a safe 1:1
lookup, not a guess.

`compute_single_zone()` filters `CLOSED_SINCE_JAN` by `oa == <this zone's OA>` to populate each
zone's `closed_stores` / `n_closed`; `compute_fop_data()` flattens all zones' lists into a
top-level `closed_stores` key in `FOP_DATA`, which `fz_dashboard.html`'s `closedStoreCount()`
reads directly (note: `FOP_DATA` is a top-level `const`, not a `window` property — reference it
directly, `window.FOP_DATA` is `undefined`).

## 3. Generation pipeline (`main()` in `generate_reports.py`)

```
load_data()                  → raw_df (Snowflake 5-Star pull + store list join)
filter_analysis_data(raw_df) → df (Open stores, current year, valid score; also captures
                                     CLOSED_SINCE_JAN before the Open filter — see §2)
enrich_with_snowflake(df)    → adds FSCC/Brand actual visit results where available
classify_tier / get_binding  → per-row _tier, _binding columns
load_workshops(df)           → Boot Camp / Rising Star attendance, joined to scores
compute_leadership(df)       → national rollup (leadership_summary.html)
compute_all_zones(df)        → per-OA-zone data (zone_scorecards.html)
compute_fop_data(...)        → Director/FOP/Franchisee rollup (fz_dashboard.html)
compute_rising_star(...)     → cross-zone Tier 2 targeting (rising_star.html)
compute_brief_data(...)      → leadership_brief.html
generate_*_html(...)         → write each HTML file via replace_data_block()
```

Months are **auto-detected from the data**, not hardcoded — `PERIOD_MONTHS`, `MONTH_LABELS`,
`PERIODS`, `REPORT_YEAR` are set once in `filter_analysis_data()` and threaded through
everywhere else. `MAX_INCLUDE_MONTH` caps which months are considered "landed" (ignores
incomplete future-month placeholders in the source).

## 4. Tier, status, and binding formulas

```python
TIER_THRESHOLD   = 2.5   # T1 < 2.5, T2 2.5–4.0, T3 >= 4.0
DEFAULT_THRESHOLD = 2.0  # "Failure to Satisfy" per Brand Standards Manual
```

**Tier** (`classify_tier(score)`): `< 2.5` → 1 (Bootcamp), `2.5–4.0` → 2 (Rising Star), `>= 4.0`
→ 3 (Top Tier). Used both on a single month's score and on a **trailing 3-month average**
(`avg3mo()` in JS / `_tier_base` in Python) depending on context — see the note in §5 on which
one each feature uses.

**Status** (computed per store in `compute_single_zone`, from the full month-by-month score
series — not read from any source column):

```python
cons_under = count of consecutive months, walking backward from the latest, scoring < 2.0
total_under = count of all months (not necessarily consecutive) scoring < 2.0

dl (Defaulting)  = cons_under >= 3  OR  total_under >= 4
ar (At Risk)     = cons_under == 2  AND NOT dl
tw (T1 Watch)    = NOT dl AND NOT ar AND latest_score is in [2.0, 2.5)
ok               = everything else
```

This mirrors the Brand Standards Manual's default language (3 consecutive periods of failure,
or 4-of-a-rolling-window) translated to the available monthly window. At-Risk is the
pre-default intervention window (2 consecutive failing months); T1 Watch is Bootcamp-tier but
not yet failing — a "get ahead of it" flag, not a contractual one.

**Binding constraint** (`get_binding(row)`): whichever of the five component star columns
(`WIN_SCORE_STAR`, `SPEED_STAR`, `BRAND_STAR`, `HB_ONTIME_STAR`, `FSCC_STAR`) is lowest for that
row. Ties broken by `BINDING_ORDER` (Win, Speed, Brand, Hutbot, FSCC). This is what every
"binding chart" / "focus bars" feature across all 5 reports visualizes.

## 5. Metrics dictionary

The full metric-by-metric formula reference (every Σ/Σ roll-up rule, star thresholds, raw
source fields) lives in **`5-STAR_METRICS.md`** — kept as its own file rather than folded in
here because it's a flat lookup table referenced constantly during development, not narrative.
The one rule that matters everywhere: **never average the averages** — for any group roll-up
(Area, Franchisee, DMA, Region, Zone, National), sum the numerator across member stores, sum
the denominator across member stores, then divide. Per-store ratios are never averaged
directly across stores; only certain scorecard *star ratings* use a volume-weighted average
(WAVG), and a few pure counters use a plain average (AVG) — `5-STAR_METRICS.md` marks exactly
which rule applies to which metric.

Star-rating thresholds (`STAR_THRESHOLDS` in `generate_reports.py`, mirrored as
`PCT_BAND_THRESHOLDS` in `fz_dashboard.html` — **keep both in sync** if these ever change):

| Metric | 1★ | 2★ | 3★ | 4★ | 5★ |
|---|---|---|---|---|---|
| Win Score | <49% | 49–60% | 60–66% | 66–71% | ≥71% |
| Speed | <40% | 40–60% | 60–70% | 70–80% | ≥80% |
| Hutbot On Time | <80% | 80–85% | 85–90% | 90–95% | ≥95% |

Overall 5-Star blend weights: Win 0.35 · Speed 0.30 · Hutbot 0.20 · Brand 0.075 · FSCC 0.075
(provided pre-blended as `OVERALL_FIVESTAR`, not recomputed by this codebase).

**Known gap (flagged, not fixed):** the Brand Standards Manual says a failed FSCC score should
cap a store at 1★ regardless of other components; the actual blend only weights FSCC at 7.5%,
so a store can fail food safety and still land in Tier 2/3. The reports compute the formula as
specified, not the policy override — see `FUNCTIONAL_SPEC.md` for the escalation options.

## 6. Boot Camp / Rising Star workshop logic

**Baseline:** an average of available 5-Star scores *before* the workshop. The anchor month
depends on the workshop day of month: on/after the 15th → anchor = `workshop_month - 1`
(prior month's data is already available); before the 15th → anchor = `workshop_month - 2`.
Baseline = average of whatever of (anchor-2, anchor-1, anchor) actually has data — 1, 2, or 3
months, never requires all three.

**Follow-ups**, counted from the month *after* the workshop: 30-day = month 1 after; 60-day =
average of months 1–2 after; 90-day = average of months 1–3 after. Same "use whatever months
exist" rule. Export always includes a `CHANGE` column = latest available check-in minus
baseline.

**Attended vs. measurable split:** a store counts as having "had a Boot Camp" the moment it has
any past workshop date, regardless of how recently. It only becomes **measurable** once it has
reached the 30-day follow-up point — this prevents stores that attended last week from diluting
the improvement averages before they've had a chance to show a result. `_bc_fact()` in
`compute_single_zone` returns `measurable: False` for attended-but-too-recent stores instead of
dropping them, so "Had Boot Camp" counts and "Measurable (30+ days)" counts can both be shown
side by side (every Boot Camp Effectiveness table across the suite has both columns).

**Control group:** for effectiveness comparisons, control = stores in the same tier at the
baseline month (Tier 1 for Boot Camp, Tier 2 for Rising Star) that did **not** attend that type
of workshop — i.e. "did attendees improve more than their tier peers who didn't attend."

**Tier 1 Boot Camp Coverage** (Zone Scorecards): denominator is the **current** Tier 1
population — stores whose **trailing 3-month average** (`avg3mo(s, n)`, not a single month)
classifies as Tier 1 right now, not the frozen January cohort. Of those, a store counts as
covered if it `bch` (ever held a Boot Camp) or `bcs` (has one scheduled). Rendered as a donut
(Had / Scheduled / Need, colored pine/gold/cardinal) with the coverage % centered, next to the
three Progress cards. A separate worklist below it surfaces Tier 1 stores that weren't Tier 1
back in January (churn into Tier 1 since the baseline) and still have no Boot Camp held or
scheduled — this is deliberately a different population from the headline coverage number,
because the original program goal was framed around the January cohort specifically.

## 7. File manifest

| File | Role |
|---|---|
| `generate_reports.py` | The generator. Everything above lives here. |
| `leadership_summary.html`, `fz_dashboard.html`, `zone_scorecards.html`, `rising_star.html`, `leadership_brief.html` | The 5 generated reports — self-templating, see §1. |
| `fz_dashboard_detail.js` | Companion data file for `fz_dashboard.html`. ~15 MB of per-store drill-down-only fields (metric-panel parts, sentiment trends, component history) that would otherwise bloat the main file's up-front load (was 19.7 MB → 5.4 MB after the split). Lazy-loaded on first franchisee drill-down via `ensureDetailLoaded()`. **Must ship in the same folder as `fz_dashboard.html`** — it degrades gracefully without it (drill-down fields just render absent), but store-level detail breaks. |
| `FUNCTIONAL_SPEC.md` / `TECHNICAL_SPEC.md` | This doc pair. |
| `5-STAR_METRICS.md` | Full metric formula/roll-up reference (§5). |
| `PHLogo.png` | Masthead logo, embedded in every report. |
| `.env` | Local secrets (Snowflake/Anthropic config) — **never committed**, see `.gitignore`. |
| `push_to_prod.sh` | Deploy script — see §8. |
| `5-Star full.csv`, `Alignment.csv`, `Workshops.csv`, `Store List - *.csv`, `OAs.xlsx` | Local data inputs — gitignored, never pushed (business-sensitive; two of the three have live Snowflake replacements per §2). |
| `_summaries.json` | Local LLM-summary cache (see §9) — gitignored, local-machine scratch, never pushed. |

**Public-repo hygiene:** this repo is public on GitHub. Only the generator, the 5 generated
reports, the companion JS file, docs, and the logo are pushed — never raw CSV/Excel source
data, `.env`, or the summary cache, even though some of those were committed in the repo's
early history before this convention was established. If you ever see a data file show up as
tracked in `git status`, it needs `git rm --cached` + a `.gitignore` entry, not just "leave it
alone."

## 8. Deploy

```bash
bash push_to_prod.sh "<commit message>"
```

Stages a fixed allowlist of files (`FILES=(...)` at the top of the script — the same "generator
+ reports + docs + logo" set from §7, nothing data-shaped), commits, and pushes to
`origin main` on `github.com/prognar/5-Star` (currently public; team-only access is a planned
follow-up, not yet done). It deliberately does **not** `git add -A` — if you add a new file
that should ship, add it to the `FILES` array explicitly.

## 9. LLM summaries (optional layer)

Every narrative paragraph (National Insight, per-FOP/per-zone summaries, Leadership Brief
recognition copy) is generated via the Claude API (`anthropic` Python SDK, `call_claude()` in
`generate_reports.py`), model `claude-sonnet-5-5` by default (`ANTHROPIC_MODEL` env var to
override). Credentials: `ANTHROPIC_API_KEY` in `.env` (or an `ant auth login` profile); add
`ANTHROPIC_WORKSPACE_ID` in `.env` too if the key is an org key not scoped to one workspace
(read only from `.env` itself, never an ambient shell var, so it can't leak onto unrelated
requests). If the API is unavailable or auth fails, `call_claude()` sets `_LLM_UNAVAILABLE` on
the first failure (so ~20 subsequent summary calls in a run fail fast instead of each retrying
a doomed request) and every report falls back to **deterministic, data-driven summaries** —
reports always have content, with or without API access.

Results are cached in `_summaries.json`, keyed so they only regenerate when the report's month
range changes — **not** when the generation code/prompts change. After editing any
summary-generation logic, delete `_summaries.json` to force fresh output.

## 10. Verification

```bash
python generate_reports.py --run-date <YYYY-MM-DD>
```

`--run-date` stamps the "data through" freshness label on `leadership_summary.html` /
`leadership_brief.html` and is required — calling `main()` without it currently raises
(`run_date.month` on `None`), so always pass it.

`scripts/_verify_five.py` (local, not part of the pushed fileset) does a structural sanity pass
over all 5 generated files — JS-parseable (`esprima`), expected data keys present — useful after
any change that touches `replace_data_block()` or the data-embedding format itself.
