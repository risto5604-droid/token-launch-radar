# Day 3 notes — token-radar-01 (2026-11-26)

Plan: dashboard + farm plans + 3 screenshots + dossier + repo assembly.
Build ONLY — no bundle, no check, no submit (Day 4). This file is Day 3.

## 1. Farm plans — DONE, verified by hand

- **New `scripts/gen_farm_plans.py`** — reads `out/board.json` +
  `data/families.json` (+ the raw snapshot for chain *names* only;
  `families.json` carries only the chain count) and writes
  `data/farm_plans.json`: **739 plans**, keyed by family key.
- One template per category (Risk Curators, Lending, Dexs, Derivatives,
  Yield, RWA, CDP, Farm, Launchpad, Bridge, Liquid Staking, OTHER),
  3–5 steps each, every step carrying the snapshot fields it is
  grounded in (`evidence`). A points program is only ever mentioned as
  "check the protocol's docs for a points program" — **0 plans assert
  one exists** (checked mechanically); 0 steps lack evidence.
- Verified by hand vs Steakhouse / Sentora / Veda: chain lists, TVL
  ($2.55B / $2.76B / $1.45B), ages (551 / 416 / 640 days), URLs,
  twitters, and implied FDVs ($618.1M / $672.6M / $392.8M) all match
  the board. Sentora's family key is `parent#sentora`, not
  `sentora-curator` — the generator keys by board `key`, so it works.
- **Deviation from FARM_PLAN.md:** the board has 57 categories, the
  plan names 12 templates. Close kin map onto the named templates
  (Yield Aggregator → Yield, Onchain Capital Allocator → Risk Curators,
  DEX Aggregator → Dexs, Liquid Restaking → Liquid Staking,
  CDP Manager → CDP, bridge-family categories → Bridge); everything
  else uses OTHER. Veda (Onchain Capital Allocator) therefore gets the
  Risk Curators template, which fits it.

## 2. Dashboard — DONE, deterministic

- **New `scripts/gen_dashboard.py`** — reads `out/board.json` +
  `data/farm_plans.json` + `data/comps.json` +
  `data/coingecko_markets.json`, writes `dashboard/`:
  `index.html` (1.26 MB, data embedded at build time so it opens from
  disk with zero requests — `fetch()` of a local file is blocked in
  Chrome, so the embedded copy is the load path), `app.js` (7.5 KB),
  `data.json` (1.26 MB, same payload as a machine-readable artifact).
- Board table: all 739 rows, sortable (rank / TVL / implied FDV /
  launch odds / EV), filterable (category dropdown, min TVL, min launch
  odds, text search). Every implied FDV shows its 80% interval next
  to it, never alone. Detail view per protocol (click a row, or
  `?detail=<key>`): implied FDV + interval, launch probability, EV,
  farm plan with evidence tags, and the 3 nearest launched comps by
  category + TVL with FDVs (same-category first by |log TVL ratio|,
  filled from all launched comps; FDV from the markets table,
  `markets[id] = [mcap, fdv]` — verified against bitcoin/ethereum/
  uniswap). 733 of 739 rows have a same-category comp; all 739 have 3.
- "How to read this board" block states the honest numbers
  (walk-forward 3.20×, 80% band ×10.2, AUC 0.70) — no overselling.
- Deterministic: two runs write byte-identical `dashboard/` files
  (sha256 checked).
- **Bug found and fixed during the build:** the first `app.js` had a
  JS syntax error (`"<tr data-key=""`) — Python's triple-quoted
  strings collapse `\"` to `"`, so the `\"` escapes I wrote in the
  generator never reached the file. Caught by `node --check` and by
  the Playwright run timing out on `#rows tr` (0 rows rendered), not
  shipped. Fixed by using single-quoted JS strings throughout
  `APP_JS` (no backslash escapes anywhere in the generator now).

## 3. Screenshots — DONE, real captures, visually inspected

- **New `scripts/shoot_dashboard.py`** — serves `dashboard/` on
  localhost, opens it in headless Chromium (Playwright install in
  the airdrop-agent venv, `chromium-1255`), captures 3 PNGs at
  1280×860 into `screenshots/`:
  - `1-board.png` (158,100 B) — board top, ranks 1–10 visible.
  - `2-detail.png` (170,926 B) — Steakhouse detail: $618.1M FDV,
    $60.7M–$6.30B interval, 50.8% launch odds, $314.1M EV, 5-step
    farm plan, 3 comps.
  - `3-filtered.png` (157,475 B) — category filter on Risk Curators,
    "57 of 739 protocols shown", only that category's rows.
- Each PNG is under 256 KiB. All three were opened and read, not just
  stat'ed: table renders, intervals show, filter is visibly applied,
  detail panel is complete.
- **Known data quirk, shown honestly:** the Risk Curators category has
  only 8 launched comps, all far smaller than Steakhouse (NAVI Lending
  $101.7M TVL / $7.4M FDV is the nearest), so the comps table shows a
  large size gap. TVL sits next to FDV in that table, so the gap is
  visible, not hidden. FDVs are the Day 1 snapshot's CoinGecko values.

## 4. Dossier + main.ts extension — DONE

- **New `src/dossier.ts`** — `buildDossier(outDir)` writes canonical
  JSON (sorted keys, no spaces), schema `token-radar/dossier/v1`:
  board summary (rows, snapshot date, top-3 with EVs), model summary
  (CV 3.43×, walk-forward 3.20×, conformal ±2.32 log / ×10.2,
  launch-odds AUC 0.70, Brier 0.221), the dashboard file list with
  sha256 + bytes, the screenshots list with sha256 + bytes, first by
  name = cover (`screenshots/1-board.png`). Modelled on the
  cooking-game kit's `makefun/dossier/v1` pattern; the schema is our
  own because the bounty defines none (see DAY2-NOTES.md §2).
- **`main.ts`** (edited in 2 turns of this session, plus a fix-up):
  imports `buildDossier`; after writing `board.json` it copies
  `dashboard/` + `screenshots/` into `MAKEFUN_OUTPUT_DIR` (throws a
  clear error if either is missing from the repo) and writes
  `out/dossier.json`. The original board log line is kept.
  One fix-up was needed: the new `const here` collided with the
  existing `here` in `main()` — renamed to `repoRoot`.

## 5. Verification (mandatory) — ALL PASS

- `scripts/verify_ts_port.py` **OVERALL: PASS** after the extension:
  determinism board.json + token_detect.json PASS; has_token 0
  mismatches / 7,376 families; gecko_id 0 mismatches; review 293
  items, same keys; board order identical; worst relative numeric
  diff 3.6e-15; top-3 **Steakhouse $314.1M / Sentora $276.9M /
  Veda $214.9M** — identical to Python.
- Full-output determinism: two fresh runs into separate dirs are
  **byte-identical** (`diff -r`: board + dashboard + screenshots +
  dossier).
- Runtime: **0.92 s** per run (grader wall budget 120 s, 1 CPU, 1 GB).
- Dossier: canonical JSON re-serialisation matches byte-for-byte;
  every listed sha256 + byte count verified against `out/`.

## 6. Repo assembly (Day 3 tail)

Ships (~4.2 MB): `main.ts`, `src/model.ts`, `src/token_detect.ts`,
`src/dossier.ts`, `data/coingecko_list.json` (960 KB) +
`data/coingecko_markets.json` (76 KB), `dashboard/`, `screenshots/`
(3 PNGs), `scripts/`, `README.md` (3 live badge lines, referral
`38hw3qgw`, topics makefun/ai-agents/bounties/trading), `LICENSE`
(MIT), `package.json`, `MODEL_CARD.md`, `DAY1/2/3-NOTES.md`,
`FARM_PLAN.md`. **NOT created yet: `.makefun/owner.json` (Day 4).**
Stays out: the 28 MB Day 1 raw data (`data/` is 30 MB total, only
the two runtime tables ship), `out/`, `input/`.

**Flag for Day 4:** the README badges assume repo
`risto5604-droid/token-launch-radar` (owner = the gh login; the repo
name is my choice, not yet created). Confirm or fix when the repo is
created — the rank/reward badge URLs embed owner/repo.

**Environment note:** `/tmp/tr-input` had been cleaned by the system
between Day 2 and Day 3; restored from `input/protocols.json`,
byte-identical to `data/protocols_raw_2026-11-26.json` (sha256
735facf0…). The verifier depends on `/tmp/tr-input` — restore it the
same way before any future run.

## 7. Winning-bar assessment (honest)

Nothing in Day 3 revealed a new defect. The model-accuracy gap from
Day 1 is unchanged (walk-forward 3.20× vs the leaders' claimed
2.26/2.99× on an unreproducible definition) — the board's edge
remains coverage + ranking + presentation, all of which Day 3
delivered and verified. No reason found to hold the entry back on
quality grounds; the submit decision is Day 4's.

## Files (Day 3)
- `scripts/gen_farm_plans.py` (new) → `data/farm_plans.json` (739 plans)
- `scripts/gen_dashboard.py` (new) → `dashboard/` (index.html + app.js + data.json)
- `scripts/shoot_dashboard.py` (new) → `screenshots/` (3 PNGs)
- `src/dossier.ts` (new) — `token-radar/dossier/v1` writer
- `main.ts` (edited) — copies dashboard/screenshots, writes dossier.json
- `README.md`, `LICENSE` (new)
- `DAY3-NOTES.md` (this file)
