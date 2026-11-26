// model.ts — fitted launch-pricing model (Day 1 scaffold).
//
// Coefficients were fitted offline (2026-11-26) on public data and are
// embedded here as constants: the grader runs with no network, so the
// entry must not fetch anything at runtime. See MODEL_CARD.md for the
// fitting procedure, the out-of-sample numbers, and what was dropped.
//
// Model 1 — implied FDV: OLS on log FDV, filtered comps (TVL >= $1M,
// FDV >= $100k, n = 445 launched protocols).
//   5-fold CV: median ratio 3.43x, R2 0.393, Spearman 0.62
//   Walk-forward (train <= 2024-06, test after): median ratio 3.20x,
//   R2 0.284, bias -0.22, Spearman 0.59, top-decile overlap 33%.
//   Split-conformal 80% band: +/- 2.321 in log space (x10.2).
//
// Model 2 — launch odds: logistic regression on mature families
// (listed >= 1y, TVL > 0, n = 3,235; base rate 48.2% have a token).
//   Held-out Brier 0.221 (base 0.250), AUC 0.70. Scored at the 1-year
//   age floor so young protocols are not punished for being young.
//
// Board rank: expected value = implied FDV x launch probability.

export interface ProtocolFeatures {
  tvl: number;
  chains: number;
  category: string;
  listedAt: number | null; // unix seconds, null when the snapshot omits it
  change7d: number | null; // fraction, e.g. 0.05 = +5% over 7d
}

// Feature order for the FDV model. Keep in sync with the beta array.
export const FDV_CATEGORIES = [
  "Bridge",
  "CDP",
  "Canonical Bridge",
  "Derivatives",
  "Dexs",
  "Farm",
  "Launchpad",
  "Lending",
  "Liquid Staking",
  "RWA",
  "Yield",
  "Yield Aggregator",
  "OTHER",
] as const;

// log FDV = beta . x ; x = [1, log TVL, cat dummies..., log chains,
// log age_days, log1p(change_7d/100), listed>=2024]
// Full precision from data/model_fdv.json (finalize refit on all
// filtered comps). Do NOT round these: the 4-decimal versions Day 1
// embedded shift log FDV by ~3e-4 (log TVL ~22 amplifies the slope
// rounding) — enough to reorder near-tied rows vs the Python build.
export const FDV_BETA = [
  4.025562191737543, 0.7184152271279168,
  1.1491145450058566, -0.6725272276847356, 1.8128637442913267, 1.3157104386862595,
  0.4708368106987811, 0.5141041567017575, 1.0711685332952499, -0.5919566590528623,
  -0.6636716800010388, 0.3841740727938817, -0.1303812735155253, -0.9701198268877385,
  0.3362465574063363,
  -0.08645604296038509, -0.01290885694014865, -0.8078195927858501, 0.5680152938293117,
];
export const FDV_CONFORMAL_Q80_LOG = 2.3214968507498055;
export const FDV_CONFORMAL_Q90_LOG = 3.069073157950122;
export const FDV_SNAPSHOT_TS = 1795400000; // 2026-11-26 UTC, fit snapshot
export const FDV_COHORT_CUT_TS = 1704067200; // 2024-01-01 UTC

// Launch-odds model: logit(p) = beta . x ; x = [1, log TVL, log age_days,
// log chains, cat dummies...] (same category list as above).
// Full precision from data/model_launch.json (same rounding note as above).
export const LAUNCH_BETA = [
  -8.848885430244817, 0.06940765413421764, 1.26694769879323, 0.04749170007355741,
  -1.0179590542492136, -0.28919414233020396, 0.2578292064236321, -0.805854663336807,
  -0.6910773542512677, 0.015667294846606224, -0.8792908599226058, -0.9584942552611783,
  -1.482119877486531, -0.7804325307951976, -0.6089523957662355, -0.8747465994902255,
  -0.7342375103685529,
];
export const LAUNCH_BASE_RATE = 0.48191653786707883;

const DAY = 86400;

function categoryIndex(category: string): number {
  const i = FDV_CATEGORIES.indexOf(category as (typeof FDV_CATEGORIES)[number]);
  return i === -1 ? FDV_CATEGORIES.indexOf("OTHER") : i;
}

function ageDays(listedAt: number | null, snapshotTs: number): number {
  // Same rule as the Python design() the model was fitted and scored
  // with (fit_model.py / finalize_model.py): an unknown listing date
  // substitutes the snapshot timestamp, i.e. age 0 clamped to 1 day —
  // NOT 365 days. (Day 1's model.ts used 365 here, which understated
  // implied FDV by ~7% for null-listedAt rows such as DeFi Saver:
  // the age coefficient is small but log(365) is not.) The launch
  // model floors the age at 365 separately in launchProbability().
  if (listedAt === null || listedAt === undefined) return 1;
  return Math.max((snapshotTs - listedAt) / DAY, 1);
}

/** Log implied FDV (USD) for a protocol, from snapshot features only. */
export function predictLogFdv(f: ProtocolFeatures, snapshotTs: number): number {
  const age = ageDays(f.listedAt, snapshotTs);
  // change7d arrives in PERCENT (DefiLlama's unit): divide by 100.
  const change = f.change7d === null || f.change7d === undefined
    ? 0
    : Math.log1p(Math.max(f.change7d / 100, -0.99));
  const x: number[] = [1, Math.log(Math.max(f.tvl, 1))];
  for (let i = 0; i < FDV_CATEGORIES.length; i++) {
    x.push(categoryIndex(f.category) === i ? 1 : 0);
  }
  x.push(
    Math.log(Math.max(f.chains, 1)),
    Math.log(age),
    change,
    f.listedAt !== null && f.listedAt !== undefined && f.listedAt >= FDV_COHORT_CUT_TS ? 1 : 0,
  );
  let s = 0;
  for (let i = 0; i < FDV_BETA.length; i++) s += FDV_BETA[i] * x[i];
  return s;
}

/** 80% conformal interval (USD) around the implied FDV. */
export function impliedFdvInterval(f: ProtocolFeatures, snapshotTs: number): {
  point: number;
  lo80: number;
  hi80: number;
} {
  const logPoint = predictLogFdv(f, snapshotTs);
  return {
    point: Math.exp(logPoint),
    lo80: Math.exp(logPoint - FDV_CONFORMAL_Q80_LOG),
    hi80: Math.exp(logPoint + FDV_CONFORMAL_Q80_LOG),
  };
}

/** P(the protocol eventually launches a token), mature-cohort model. */
export function launchProbability(f: ProtocolFeatures, snapshotTs: number): number {
  // Age floor (see MODEL_CARD.md): score at >= 1y so a protocol listed
  // last month is not punished for not having launched yet.
  const age = Math.max(ageDays(f.listedAt, snapshotTs), 365);
  const x: number[] = [
    1,
    Math.log(Math.max(f.tvl, 1)),
    Math.log(age),
    Math.log(Math.max(f.chains, 1)),
  ];
  for (let i = 0; i < FDV_CATEGORIES.length; i++) {
    x.push(categoryIndex(f.category) === i ? 1 : 0);
  }
  let z = 0;
  for (let i = 0; i < LAUNCH_BETA.length; i++) z += LAUNCH_BETA[i] * x[i];
  z = Math.max(-30, Math.min(30, z));
  return 1 / (1 + Math.exp(-z));
}

export interface ScoredProtocol {
  impliedFdvUsd: number;
  impliedFdvLo80Usd: number;
  impliedFdvHi80Usd: number;
  launchProbability: number;
  expectedValueUsd: number;
}

/** One-call scoring for a protocol: implied FDV with its 80% conformal
 *  interval, launch probability, and the expected value the board ranks
 *  by (implied FDV x launch probability). */
export function scoreProtocol(
  f: ProtocolFeatures,
  snapshotTs: number,
): ScoredProtocol {
  const interval = impliedFdvInterval(f, snapshotTs);
  const p = launchProbability(f, snapshotTs);
  return {
    impliedFdvUsd: interval.point,
    impliedFdvLo80Usd: interval.lo80,
    impliedFdvHi80Usd: interval.hi80,
    launchProbability: p,
    expectedValueUsd: interval.point * p,
  };
}
