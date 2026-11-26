# Farm-plan generator + Day 3 run order — token-radar-01 (Day 2, 2026-11-26)

Day 3 builds the dashboard, the farm plans, the 3 screenshots, and the
dossier. This file is the plan Day 3 runs follow, in order. Nothing
here is built yet — Day 3 is a separate session.

## Inputs (all ready)

- `out/board.json` from `main.ts` — 739 scored rows (verified
  TS/Python agreement, see DAY2-NOTES.md).
- `data/families.json` — per-family snapshot fields (TVL, chains,
  category, listedAt, url, twitter, description) for farm-plan text.
- Requirements (`../token-radar-01-requirements.json`): README uses the
  3 LIVE badge lines from `how_to_submit.readme_template` (referral
  code 38hw3qgw); About topics `makefun, ai-agents, bounties, trading`
  (note: requirements say **trading**, not the skill's `growth`);
  homepage `https://make.fun/bounty/token-radar-01`. Entry is
  program/v1: `main.ts` at repo root, Node 22, 120 s wall / 1 CPU /
  1 GB, 2-run determinism.
- Reference pattern on disk (no `vendor/makefun-board.ts` exists —
  see DAY2-NOTES.md): the cooking-game kit's starter
  (`../best-cooking-game-20261125-0137-kit/.../starter/`): `main.ts`
  copies `game/` + `screenshots/` to `MAKEFUN_OUTPUT_DIR` and writes
  `dossier.json` via `vendor/makefun-game.ts` (`buildDossier`,
  `makefun/dossier/v1`); `serve.ts` serves the app locally;
  `shots.json` lists the shots; screenshots are PNG/JPEG, first by
  name is the cover.

## Generators, in order

### 1. `scripts/gen_farm_plans.py` — farm plans (FIRST)

Reads `data/families.json` + `out/board.json`, writes
`data/farm_plans.json` (keyed by family key).

- One template per category (Risk Curators, Lending, Dexs,
  Derivatives, Yield, RWA, CDP, Farm, Launchpad, Bridge, Liquid
  Staking, OTHER), each with 3–5 steps grounded ONLY in snapshot
  fields: which chains the protocol is on, its TVL tier, its age,
  its URL/twitter for the official links.
- Per-protocol instantiation fills in the protocol's name, chains,
  TVL, and category; no invented facts. A points program may only
  be mentioned as "check the protocol's docs for a points program"
  — the snapshot has no points field, so never assert one exists.
- Each plan carries its evidence: the snapshot fields it used.
- Verify by hand against 3 real protocols (Steakhouse, Sentora,
  Veda): every step must be traceable to a snapshot field; fix the
  template, not the individual plan, when a step is wrong.

### 2. `scripts/gen_dashboard.py` — dashboard (SECOND, needs 1)

Reads `out/board.json` + `data/farm_plans.json`, writes `dashboard/`:

- `dashboard/index.html` + `dashboard/app.js` + `dashboard/data.json`
  (the 739 rows + plans, embedded at build time). Static, offline:
  no CDN, no network request, no external font — the grader's
  sandbox has no network and the dashboard must open from disk.
- Board table: all 739 rows, sortable (rank, TVL, implied FDV,
  launch odds, EV), filterable (category dropdown, min TVL, min
  launch odds, text search). Shows the 80% interval next to every
  implied FDV — never the point estimate alone.
- Detail view per protocol (click a row): implied FDV + interval,
  launch probability, EV, farm plan, and the 3 nearest launched
  comps by category + TVL (from `data/comps.json`) with their FDVs.
- A short "how to read this board" block stating the honest numbers
  (walk-forward 3.20×, 80% band ×10.2) — no overselling.
- Deterministic output: same inputs write byte-identical files
  (sorted keys, fixed ordering, no timestamps).

### 3. Screenshots (THIRD, needs 2)

Serve `dashboard/` locally (`node serve.ts` pattern from the
cooking-game starter, or `python3 -m http.server`), open in a
headless browser, capture 3 PNGs into `screenshots/`:

1. `1-board.png` — the board table (top of the ranking visible).
2. `2-detail.png` — a protocol detail view (Steakhouse, rank 1).
3. `3-filtered.png` — a filtered view (e.g. category filter on, or
   min-TVL filter on, visibly applied).

- First check the VM for a browser: Playwright Chromium is installed
  for the airdrop-agent venv (`~/workspace/airdrop-agent`); else
  `which chromium chromium-browser google-chrome firefox`. If no
  browser is usable on the VM, say so in the Day 3 report — do NOT
  fake screenshots.
- Screenshots must be real captures of the dashboard running, not
  composed images. Keep each PNG under 256 KiB where possible (the
  game kit's cap; the radar requirements set no cap, but small is
  safer for the repo).

### 4. `src/dossier.ts` + `main.ts` extension (FOURTH, needs 2 + 3)

There is no vendor dossier writer for this bounty, so Day 3 writes
its own, modelled on the game kit's `makefun/dossier/v1` pattern:

- `src/dossier.ts`: `buildDossier(outDir)` — canonical JSON (sorted
  keys, no spaces) with: schema `token-radar/dossier/v1`, board
  summary (rows, snapshot date, top-3 with EVs), model summary (CV
  3.43×, walk-forward 3.20×, conformal ±2.32 log, launch-odds AUC
  0.70), the dashboard file list with sha256 + bytes, the
  screenshots list with sha256 + bytes (first by name = cover).
- Extend `main.ts` (genuine edits, in ≥2 turns of the Day 3 session,
  for the thinking_revised gate): after writing `board.json`, copy
  `dashboard/` and `screenshots/` beside it into
  `MAKEFUN_OUTPUT_DIR` and write `out/dossier.json` via
  `buildDossier`. The grader's run must reproduce the handed-in
  output — the dashboard and screenshots ship in the repo AND are
  regenerated by `main.ts`.
- Re-run `scripts/verify_ts_port.py` after the extension: board
  agreement + determinism must still PASS.

### 5. Repo assembly (Day 3 tail / Day 4 boundary)

Files the entry repo ships (commit on Day 4, NOT before):

- `main.ts`, `src/model.ts`, `src/token_detect.ts`, `src/dossier.ts`
- `data/coingecko_list.json`, `data/coingecko_markets.json` (runtime
  tables only — ~1.05 MB)
- `dashboard/`, `screenshots/` (3 PNGs)
- `scripts/` (build/verify/generator scripts — the build story)
- `README.md` (3 live badge lines), `LICENSE` (MIT), `package.json`
  (`{"type": "module"}` — already added), `.makefun/owner.json`
  (Day 4, primary wallet — verify before submit, per skill)
- `MODEL_CARD.md`, `DAY1-NOTES.md`, `DAY2-NOTES.md`, `FARM_PLAN.md`

Files that must NOT ship: the 28 MB Day 1 raw data
(`data/protocols_raw_*.json`, `data/fees_raw_*.json`,
`data/families.json`, `data/comps.json`, `data/watchlist*.json`,
`data/token_match_review.json`, `data/model_*.json`,
`data/coingecko_list_2026-11-26.json`,
`data/coingecko_markets_2026-11-26.json`) — build-time inputs only.
`out/` and `input/` (local run dirs) also stay out.

## Day 4 (separate approval, NOT this task)

Bundle with recorded sessions (skill flags: `--mcp none --provider
meta --effort default`, `--prompt-file`, `--parent-session`,
`--no-discover`), `makefun check` (the Day 4 fixer session must make
its own 2 genuine edits to a counted file in 2 turns of one session
before bundling — the skill's lesson: one edit in a separate session
does NOT count), submit via the CLI kit. NO submit before Day 4.
