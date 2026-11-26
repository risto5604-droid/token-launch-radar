# Model card — token launch radar (Day 1, 2026-11-26)

## What the board ranks by

**Expected value = implied FDV × launch probability.** Implied FDV is the
steady-state value a launch would converge to, calibrated on launched
protocols; launch probability is the chance the protocol ever launches a
token. Both are shown with their uncertainty — the point estimate alone
would be dishonest at this error level.

## Data (all public, snapshot 2026-11-26)

- **DefiLlama** `GET /api/llama.fi/protocols` — 9,116 protocols
  (`data/protocols_raw_2026-11-26.json`, 9.7 MB).
- **CoinGecko** `/coins/list` (21,248 coins) + `/coins/markets` (2,520 rows
  with FDV/mcap) — used to (a) detect tokens DefiLlama does not link and
  (b) get FDV/mcap for launched comps.
- **DefiLlama fees overview** (3,300 protocols) — fetched, tested, DROPPED
  (see below).
- Families: versioned entries grouped by `parentProtocol` (Aave V3,
  Morpho Blue, Uniswap V4, ...) — 7,376 families. Family TVL sums members
  except `excludeTvlFromParent`.

## Watchlist construction (the radar universe)

A family is **pre-token** when no member has a DefiLlama `gecko_id` AND no
CoinGecko coin matches it by symbol+name (scored matching: exact name 100,
coin-name-prefix 50+len, first-token prefix 60, token overlap 10; a tie is
broken by live market cap; name-only matches are confirmed only when the
coin has a quoted market cap or FDV — this rejects fake coins such as
CoinGecko's "Polymarket"/POLY, which has no market data, and
Extended/XTEN, whose claim is not open yet). 954 families were caught by
the CoinGecko cross-check that DefiLlama alone misses (Morpho, Uniswap V4,
Hyperliquid, Ethena USDe, Sky, Spark, LayerZero, ...). Two manual
overrides, each verified against a public source: M0 (docs.m0.org — POWER /
ZERO governance tokens exist, not on CoinGecko) and Cooler Loans / Saphyre
V3 / MUX Perps (products of Olympus / DragonSwap / MUX Protocol).
Ambiguous matches (279) are kept in `data/token_match_review.json`.

**Excluded as wrapped/staked products** (brief: "not a wrapped or staked
product of one that trades"): name/symbol patterns (`staked`, `wrapped`,
`wstETH`-style symbols), receipt `assetToken` (WBETH, lsETH), the whole
Liquid Staking / Liquid Restaking categories, and whole categories CEX /
Bridge / Canonical Bridge.

**Board universe: 739 protocols with TVL ≥ $50k** (2,180 with any TVL).
The $50k floor matches the leading entries' scale (~758 protocols) and
keeps dust out of the board. Top of the board: Steakhouse Financial
($2.55B TVL), Sentora Curator ($2.76B), Gauntlet ($1.59B), Veda ($1.45B) —
risk curators / capital allocators with no token.

## Model 1 — implied FDV (the pricing model)

OLS on log FDV. Training set: launched comps with TVL ≥ $1M and
FDV ≥ $100k (n = 445) — the dead-token tail was removed after round 1
showed it dominates the error (see below). Features: log TVL, category
(12 dummies + OTHER), log chains, log age (days since listing), 7d TVL
change (percent, correctly scaled), listed-≥-2024 cohort dummy.

| test | median ratio | R² | Spearman | top-decile overlap |
|---|---|---|---|---|
| 5-fold CV | **3.43×** | 0.393 | 0.62 | 48% |
| walk-forward (train ≤2024-06, test after) | **3.20×** | 0.284 | 0.59 | 33% |
| walk-forward, big protocols only (TVL ≥$10M) | 4.01× | 0.151 | 0.44 | 38% |

Split-conformal 80% prediction interval: **±2.32 in log space (×10.2)**.
Top-decile value share (CV): the predicted top 10% captures ~61% of
actual FDV. Category effects (×): Canonical Bridge 6.1, Bridge 3.1,
Derivatives 3.8, Launchpad 3.0, Dexs 1.6, RWA 1.4, Lending 0.55,
Liquid Staking 0.52, Yield Aggregator 0.38. Cohort ≥2024: ×1.76 —
listings since 2024 carry ~2.5× the FDV/TVL of 2021–23 listings.
7d TVL change coefficient is **−0.81**: a just-spiked TVL is worth less
(mean reversion / hot money).

### What was tried and dropped (blind-test discipline)

- **Unfiltered comps (n = 1,324):** CV 7.11×, walk-forward 11.5×, R² < 0.
  The dead-token tail (FDV <$100k) is noise, not signal. Filtering to
  TVL ≥$1M / FDV ≥$100k fixed most of it.
- **Per-category median FDV/TVL ratio model (slope fixed at 1):** CV
  3.83×, walk-forward R² 0.02 — OLS wins.
- **Market-cap target instead of FDV:** CV 3.79×, walk-forward R² 0.13 —
  FDV wins.
- **30d fees as a feature:** CV 3.43× → 3.61×, top-decile overlap
  40% → 33% — no gain; fees are NOT in the model (and no embedded fees
  table is needed at grading time).
- **Category TVL share:** collinear with category dummies + log TVL —
  identical metrics; dropped.

## Model 2 — launch odds

Logistic regression on mature families (listed ≥ 1y, TVL > 0, n = 3,235;
base rate 48.2% have a token). Features: log TVL, log age, log chains,
category. Held-out Brier **0.221** (base-rate 0.250), AUC **0.70**,
calibration quintiles track actual rates within ~0.06. **Age floor:**
protocols are scored at age ≥ 365d, because the model is a
mature-cohort probability — a protocol listed last month must not be
punished for not having launched yet. Known limitation: this is
P(launched once mature), not a time-to-launch forecast.

## Honest limitations (read before trusting the board)

1. **The outcome is CURRENT FDV, not FDV at launch.** A launch usually
   prices below a mature protocol's current FDV — or above it when the
   float is tiny. The model estimates steady-state value, not TGE price.
2. **The intervals are wide (×10 at 80%).** The board must show them;
   a point estimate without its band is misleading.
3. **Big protocols are the hardest to price** (walk-forward 4.01× at
   TVL ≥$10M) — brand, fees narrative, and team matter and are not in
   the snapshot. The ranking is better than the levels (Spearman 0.59).
4. **Top entries quote walk-forward ×2.26/×2.99.** Our walk-forward is
   3.20× on the same definition (median absolute ratio). Their number
   may use a different target, subset, or definition — we could not
   reproduce it from public data, and we do not claim to match it.
   The gap to close on Day 2 is likely features the snapshot does not
   have (fees did not help; what might: TVL momentum over longer
   windows, chain mix, points-program signals — all need care about
   what the sealed snapshot actually contains).
5. **Token detection is heuristic.** 279 ambiguous matches remain in
   review; a few small families may be misclassified either way. The
   big names were all hand-verified.
6. **The sealed grading snapshot may differ** from the 2026-11-26 public
   one (different date, different fields). The entry must degrade
   gracefully: unknown categories → OTHER, missing `change_7d` → 0.
   Missing `listedAt`: the FDV model scores age 1 day (the Python
   `design()` convention the model was fitted and scored with — the
   listing date substitutes the snapshot timestamp, clamped to 1 day),
   while the launch-odds model floors age at 365d. (Day 2 correction:
   an earlier draft of this card said 365d for both; the FDV side was
   wrong — see DAY2-NOTES.md.)
