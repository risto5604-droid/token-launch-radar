# Day 2 notes — token-radar-01 (2026-11-26)

Plan: Day 1–2 data + fitted model + out-of-sample tests; Day 3 dashboard
+ 3 screenshots; Day 4 bundle/check/submit. This file is Day 2 only.

## 1. CoinGecko cross-check ported to TypeScript — DONE, verified

### What was wrong
`main.ts` (Day 1) used only DefiLlama `gecko_id` for token detection,
so its watchlist had **1,060 rows** topped by tokened protocols
(Hyperliquid Bridge $1,619M EV, Ethena USDe $758M) — the CoinGecko
cross-check that catches 954 tokened families lived only in the
offline Python build.

### What changed
- **New `src/token_detect.ts`** — faithful port of
  `scripts/build_dataset.py`'s token detection: NFKD/ascii
  normalisation, token sets, scored coin matching (exact 100,
  prefix 50+len / 40, token overlap 10/token, first-token 50/60),
  strict-best-wins with a live-mcap tie-break, single-symbol
  fallback, name-only matches confirmed trading by the markets
  table (mcap > 0 or FDV > 0), provisional/ambiguous matches kept
  for human review and NOT marked tokened, the 4 manual overrides
  (M0, Cooler Loans, Saphyre V3, MUX Perps), and the flagship-only
  name-matching rule (a stray minor member can never mark a family
  tokened). `loadCoinTables()` reads the embedded tables.
- **New `data/coingecko_list.json` (980 KB) + `data/coingecko_markets.json`
  (74 KB)** — compact single-line JSON, generated offline by the new
  `scripts/build_runtime_tables.py` from the Day 1 public fetches
  (21,248 coins; 2,520 with market data). These are the only `data/`
  files the entry repo ships; the 28 MB of Day 1 raw files are
  build-time inputs and stay out (see FARM_PLAN.md).
- **`main.ts`** — `buildFamilies(protocols, tables)` now calls
  `detectToken()` per family; grouping key is `parentProtocol ||
  slug` (Python `or` parity, was `??`); `geckoId` is the
  lexicographically smallest member link (Python parity); new
  `board.json` meta (`tokenedFamilies`, `reviewItems`); debug output
  `out/token_detect.json` behind `MAKEFUN_DEBUG_TOKEN_DETECT=1`
  (per-family decisions + review list, deterministic). Header comment
  updated: no `vendor/makefun-board.ts` exists (see §2).
- **New `src/model.ts` fixes (found by the verifier, §3)** —
  full-precision betas from `data/model_fdv.json` /
  `data/model_launch.json`, full-precision conformal bands
  (2.3214968507498055 / 3.069073157950122); `ageDays(null)` is now
  1 day, not 365.
- **New `package.json`** — `{"name":"token-launch-radar",
  "private":true,"type":"module"}`; silences Node's
  MODULE_TYPELESS_PACKAGE_JSON warning so the action log is clean.
- **New `scripts/verify_ts_port.py`** — runs `main.ts` twice and
  checks determinism, family-level token agreement, review-list
  agreement, and board agreement vs the Python reference.
- **`MODEL_CARD.md`** — corrected two Day 1 figures (see §3).

### Verification (`scripts/verify_ts_port.py`, OVERALL: PASS)
- Watchlist: **739 rows**, top-3 **Steakhouse $314.1M, Sentora
  $276.9M, Veda $214.9M** — identical names and EVs to Python.
- Determinism: `board.json` and `token_detect.json` byte-identical
  across two runs.
- `has_token`: **0 mismatches across all 7,376 families**;
  `gecko_id`: **0 mismatches**.
- Review list: **293 items, same keys** both sides.
- Board order: identical; worst relative numeric diff **3.6e-15**
  (last-ulp float noise between V8 and CPython math).
- Runtime: **0.78 s per run** (grader wall budget is 120 s, 1 CPU,
  1 GB) — the matcher is far inside the budget.
- Board meta: 9,116 protocols → 7,376 families → 3,402 tokened
  excluded → 739 watchlist rows, 293 review items.

## 2. `vendor/makefun-board.ts` does NOT exist — premise corrected

Day 1 assumed a kit file `vendor/makefun-board.ts` plus a
`dossier.json` schema would be read on Day 2. Checked on Day 2:

- Searched every `*-kit/` directory on disk (excuse, haiku,
  cooking-game, tiny-stack-vm, one-liner-marathon, auto-reply, ...),
  the kit tarballs, and a full-tree grep: **no file named
  `makefun-board.ts` exists anywhere**. The only vendor file on disk
  is `starter/vendor/makefun-game.ts` in the cooking-game kit
  (game/v1 harness — read as the reference pattern, see FARM_PLAN.md).
- The token-radar requirements JSON
  (`../token-radar-01-requirements.json`) mentions **"dossier" 0
  times, "board.json" 0 times, "makefun-board" 0 times**. It is a
  program/v1 bounty: deliverables are repo_url, commit_sha,
  bundle/transcripts, title, entry_message/signature, LICENSE,
  `main.ts`, `.makefun/owner.json`. The grader runs `main.ts`
  (node22; run_completes 120 s / 1 CPU / 1024 MB; run_deterministic
  2 runs, same action log). No repo-size cap applies to this
  competition (the tree-cap check is not in its applies list), so
  the ~1.05 MB embedded CoinGecko tables are fine.
- The prerequisites DO require a dashboard + 3 screenshots (board,
  protocol detail, filtered view) — but with no vendor schema, Day 3
  defines its own `dossier.json` modelled on the game kit's
  `makefun/dossier/v1` pattern (canonical JSON manifest with sha256
  of outputs). See FARM_PLAN.md for the Day 3 generators and order.
- No kit was downloaded (per task instruction). The token-radar kit
  was never downloaded on Day 1 either.

## 3. Two real Day 1 bugs found by the verifier (fixed)

Day 1 claimed "TS/Python agree exactly on all 739 overlapping rows".
The verifier showed they did not — two systematic causes:

1. **Rounded betas.** `model.ts` embedded betas rounded to 4
   decimals; the Python refit has full precision. The log-TVL slope
   rounding alone (1.5e-05 × log TVL ~22) shifts log FDV by ~3e-4,
   i.e. ~0.04% in FDV and reordered near-tied rows (first order
   diffs at ranks 35–38, 72). Fixed: full-precision constants.
2. **Null `listedAt` age.** Day 1 `ageDays(null)` returned 365;
   the Python `design()` the model was fitted and scored with
   substitutes the snapshot timestamp, i.e. age 0 clamped to **1
   day**. For null-listedAt rows (e.g. DeFi Saver) this understated
   implied FDV by ~7.4% (log-age coefficient −0.0129 × log 365).
   Fixed: `ageDays(null)` → 1. The launch-odds model still floors
   age at 365 (that matches Python `launch_odds`). The MODEL_CARD
   line claiming "missing listedAt → 365d age" was corrected, and
   its top-EV figures were corrected too: the card quoted $331M /
   $307M / $233M / $227M / $112M (from the rounded-beta TS run);
   the Python reference values are $314M / $277M / $215M / $188M /
   $107M — now matched by TS to 3.6e-15.

## 4. What remains for Day 3

Per FARM_PLAN.md, in order: (1) `scripts/gen_farm_plans.py`
(per-category templates, snapshot fields only, verify vs Steakhouse /
Sentora / Veda); (2) `scripts/gen_dashboard.py` (static offline
dashboard: sortable/filterable 739-row table, per-protocol detail
with interval + launch odds + farm plan + comps); (3) 3 screenshots
(board / detail / filtered) with a real headless browser — check
Playwright Chromium in the airdrop-agent venv first; (4)
`src/dossier.ts` + `main.ts` extension (copy dashboard/ +
screenshots/ to output, write `dossier.json`; genuine edits in ≥2
turns of the Day 3 session); re-run the verifier; (5) repo assembly
list (README with 3 live badge lines, About topics
makefun/ai-agents/bounties/**trading**, LICENSE MIT,
`.makefun/owner.json` on Day 4).

Day 4 (separate approval): bundle/check/submit. The Day 4 fixer
session still needs its own 2 genuine edits to a counted file in 2
turns of one session before bundling (skill lesson — one edit in a
separate session does not count for `thinking_revised`).

## Files (Day 2)
- `src/token_detect.ts` (new, 13.8 KB) — the ported matcher
- `src/model.ts` (edited) — full-precision betas, null-age fix
- `main.ts` (edited, 2 passes) — detector integration, board meta
- `package.json` (new) — `{"type": "module"}`
- `data/coingecko_list.json` (new, 980 KB) + `data/coingecko_markets.json` (new, 74 KB)
- `scripts/build_runtime_tables.py` (new) — generates the two tables
- `scripts/verify_ts_port.py` (new) — the cross-check verifier
- `MODEL_CARD.md` (edited) — listedAt + top-EV corrections
- `FARM_PLAN.md` (new) — Day 3 generator plan + run order
- `DAY2-NOTES.md` (this file)
