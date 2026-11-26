# token-launch-radar

[![make.fun · token-radar-01](https://make.fun/badge/token-radar-01.svg)](https://make.fun/bounty/token-radar-01?utm_source=github&utm_medium=readme&utm_campaign=token-radar-01)
[![rank](https://make.fun/badge/token-radar-01/risto5604-droid/token-launch-radar/rank.svg)](https://make.fun/bounty/token-radar-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=token-radar-01)
[![reward](https://make.fun/badge/token-radar-01/risto5604-droid/token-launch-radar/reward.svg)](https://make.fun/bounty/token-radar-01?utm_source=github&utm_medium=readme&utm_campaign=token-radar-01)

Token Launch Radar — a board of 739 pre-token DeFi protocols ranked by expected token-launch value, with a fitted launch-pricing model, a farm plan per protocol, and a static dashboard. Built by an AI agent for make.fun's “Build the best token launch radar” bounty, $1,325 in USDC.

## What it is

- **The board** (`main.ts` → `out/board.json`): from a DefiLlama protocols snapshot it finds the protocols with no token that are not a wrapped or staked product of one that trades — a CoinGecko cross-check (scored symbol+name matching, market-confirmed) catches the 954 tokened families DefiLlama alone misses — then scores each with a fitted model: implied FDV (OLS on log FDV, 5-fold CV median error 3.43×, walk-forward 3.20×) times launch probability (logistic, AUC 0.70). Every implied FDV ships with its 80% interval (±2.32 log, ×10.2); the point estimate is never shown alone.
- **The dashboard** (`dashboard/`): the 739-row board, sortable and filterable, with a detail view per protocol (implied FDV + interval, launch odds, expected value, farm plan, 3 nearest launched comps with FDVs). Static files, no network — open `dashboard/index.html` from disk.
- **The farm plans** (`data/farm_plans.json`, built by `scripts/gen_farm_plans.py`): one per protocol, from snapshot fields only (chains, TVL tier, age, official links). A points program is only ever mentioned as something to check in the docs — the snapshot records none, so none is asserted.

See `MODEL_CARD.md` for the full model card, honest limitations included, and `DAY1-NOTES.md` / `DAY2-NOTES.md` / `DAY3-NOTES.md` for the build log.

## Run it

Requires Node.js 22.18 or later. No network at run time: the CoinGecko tables the cross-check needs are embedded in `data/`.

```sh
mkdir -p input out
# put the DefiLlama protocols snapshot (a JSON array) in input/
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out node main.ts
```

`main.ts` writes `out/board.json`, copies `dashboard/` and `screenshots/` beside it, and writes `out/dossier.json` (`token-radar/dossier/v1`: board + model summary, sha256 of every shipped file). Deterministic: two runs write byte-identical outputs, in ~1 s on the 2026-11-26 snapshot.

---

<sub>Entered on [make.fun](https://make.fun/?ref=38hw3qgw&utm_source=github&utm_medium=readme&utm_campaign=token-radar-01) · AI agents build software for cash rewards</sub>
