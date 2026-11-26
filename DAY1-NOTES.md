# Day 1 notes — token-radar-01 (2026-11-26)

Plan: Day 1–2 data + fitted model + out-of-sample tests; Day 3 dashboard
+ 3 screenshots; Day 4 bundle/check/submit. This file is Day 1 only.

## Done

### Dataset (`data/`, 28 MB)
- DefiLlama protocols snapshot 2026-11-26: 9,116 protocols, 7,376
  families (parentProtocol-grouped). CoinGecko list (21,248 coins) +
  markets (2,520 rows, FDV/mcap). Fees overview (3,300 protocols).
- Token detection: DefiLlama `gecko_id` + CoinGecko symbol+name matching
  (scored, mcap tie-break, markets-confirmed name-only matches).
  954 families caught by the cross-check that DefiLlama alone misses.
  Manual overrides (verified): M0 (POWER/ZERO exist), Cooler Loans,
  Saphyre V3, MUX Perps. 279 ambiguous matches in
  `token_match_review.json`.
- Exclusions: CEX / Bridge / Canonical Bridge categories; wrapped/staked
  products (name/symbol/assetToken/category rules).
- **Watchlist: 739 protocols (TVL ≥ $50k)** — same scale as the leading
  entries' 758. 2,180 with any TVL. `watchlist_scored.json` has implied
  FDV + 80% interval + launch odds + expected value + rank for all 739.
- Scripts: `scripts/build_dataset.py`, `fetch_markets.py`,
  `fit_model.py`, `fit_model2.py`, `fit_model3.py`, `finalize_model.py`.
  All deterministic (hash folds, no wall-clock dependence).

### Model (see MODEL_CARD.md for the full card)
- Implied FDV: OLS on log FDV, filtered comps (TVL≥$1M, FDV≥$100k,
  n=445). 5-fold CV median ratio **3.43×**, R² 0.393, Spearman 0.62.
  Walk-forward (train ≤2024-06): **3.20×**, R² 0.284, bias −0.22,
  Spearman 0.59, top-decile overlap 33%, top-decile value share ~61%.
  Conformal 80% band ±2.32 log (±×10.2).
- Launch odds: logistic, AUC 0.70, Brier 0.221 vs 0.250 base.
- Board rank: expected value = implied FDV × launch probability.
- Top EV: Steakhouse $331M, Sentora $307M, Veda $233M, Gauntlet $227M,
  Upshift $112M. Top implied FDV: Sentora $673M, Steakhouse $618M.
- Dropped after blind tests: fees (no gain), mcap target, median-ratio
  model, category-share (collinear). See MODEL_CARD.md.

### Code scaffold (`main.ts`, `src/model.ts`)
- Fitted coefficients embedded as constants; no network at runtime.
- `main.ts` loads a snapshot, builds families, filters the watchlist,
  scores, writes `out/board.json`. Verified: deterministic (two runs
  byte-identical) and TS/Python agree exactly on all 739 overlapping
  rows (after fixing two real bugs found by the cross-check — see below).
- Files were written across multiple messages with genuine edits
  (thinking_revised discipline started; a Day 4 fixer session still
  needs to make its own 2 edits in 2 turns of one session before
  bundling, per the skill).

### Bugs caught by cross-checks (kept here so they are not repeated)
1. **OTHER category never fired in Python scoring** — `design()` did
   not map rare categories to OTHER, so Risk Curators / Onchain Capital
   Allocator rows lost the ×1.43 OTHER effect. Fixed in
   `finalize_model.py` (mapping inside `design()`); TS was already
   correct. This moved the top-4 implied FDVs up ~43%.
2. **DefiLlama `change_7d` is in PERCENT, not a fraction** — the
   unscaled version clamped 70% of rows to −0.99. Fixed in all three fit
   scripts + `model.ts` (divide by 100). Correctly scaled, the
   coefficient is −0.81 (spiked TVL is worth less).
3. **A stray minor member can poison family matching** — "Stellar DeFi
   Hub" grouped under Sentora falsely marked it tokened (Stellar).
   Name matching now scores only the flagship member + parent slug.
4. **CoinGecko lists fake/unofficial coins** (Polymarket/POLY, no market
   data) — name-only matches require a quoted mcap or FDV.

## Honest gap vs the top entries

- Our walk-forward is **3.20×** (median absolute ratio); the leaders
  quote ×2.26/×2.99 — on an unknown definition/target. We could not
  reproduce their number from public data. The model is real and
  defensible (Spearman 0.59 walk-forward, top-decile value share 61%),
  but **on model accuracy alone this is not yet a top-10 entry**: the
  80% bands are ×10 wide and big-protocol pricing is the weakest part
  (4.01×). The board's edge must come from coverage + ranking +
  presentation (farm plans, detail views, intervals shown honestly),
  plus whatever Day 2 feature work can still buy.
- Do NOT oversell the model to the judge: show intervals, show the
  launch odds, and let the ranking speak. A fake-narrow interval would
  be caught by anyone who checks.

## Day 2 / Day 3 — what is still missing

### Day 2 (model + entry hardening)
1. **Port the CoinGecko cross-check to TypeScript** (or embed the
   tokened-family list). Right now `main.ts` uses only DefiLlama
   `gecko_id`, so its watchlist has 1,060 rows and its top-3 are
   tokened protocols (Hyperliquid, Ethena, Uniswap V4) — WRONG until
   this is ported. The Python-side list is `data/families.json`
   (`has_token` + `gecko_id`); the cleanest runtime-safe approach is an
   embedded `tokened.json` (slug → gecko_id) generated from the offline
   build, with the DefiLlama link as fallback. Decide: embedded list
   (stale if the sealed snapshot is newer) vs re-implementing the
   matcher in TS (needs the CoinGecko list embedded — 1.4 MB — and the
   markets table for confirmation; heavy but self-contained).
2. **Confirm the sealed `/input` layout.** The kit was deliberately NOT
   downloaded on Day 1, so `vendor/makefun-board.ts` and the dossier
   format are still unknown. Day 2: download the kit (allowed then),
   read `vendor/makefun-board.ts`, and align `main.ts` I/O with it
   (input filenames, `dossier.json` schema, `board.json` schema).
3. **Farm-plan generator** (per category + per protocol, from snapshot
   fields only): the board needs a farm plan per row. Draft templates
   per category on Day 2; verify against a few real protocols.
4. **Optional model stretch (only if it wins OOS):** longer-window TVL
   momentum (needs historical TVL — the snapshot may not have it;
   check), chain-mix quality, points-program signals. Do NOT add a
   feature without a CV/walk-forward win.
5. Re-verify TS/Python agreement after the matcher port, and re-run
   the determinism check.

### Day 3 (dashboard + screenshots)
- `dashboard/` static page, no network: board table (739 rows,
  sortable/filterable), detail view per protocol (implied FDV + interval
  + launch odds + farm plan + comps), filter control.
- 3 screenshots: board, protocol detail, filtered view (browser).
- `dossier.json` via `vendor/makefun-board.ts`.
- README with make.fun badges (3 live badge lines, NOT the generic
  badge — see skill), `.makefun/owner.json`, LICENSE (MIT).

### Day 4 (submit — separate approval, NOT this task)
- Bundle with recorded sessions (see skill for the exact flags),
  `makefun check` (thinking_revised: files need ≥2-message edits —
  already started on Day 1, fixer session to add its own), submit via
  CLI kit. NO submit before Day 4.

## Files
- `data/` — raw + built datasets, model JSONs (28 MB)
- `scripts/` — dataset build, markets fetch, fitting (rounds 1–3), finalize
- `src/model.ts` — fitted model (embedded coefficients)
- `main.ts` — entrypoint scaffold (writes `out/board.json`)
- `MODEL_CARD.md` — full model card
- `DAY1-NOTES.md` — this file
