#!/usr/bin/env python3
"""Finalize the winning model (round 3 verdict) and score the watchlist.

Winner: OLS on log FDV, filtered comps (TVL>=1M, FDV>=100k, n=445),
features = log TVL + category + log chains + log age + change_7d +
listed>=2024 cohort dummy. Fees tested and DROPPED (no OOS gain).
Category-share tested and DROPPED (collinear with category dummies).
mcap target tested and DROPPED (FDV wins).

Outputs:
  - data/model_fdv.json (refit on all filtered comps + conformal band)
  - data/watchlist_scored.json (739 rows, TVL>=50k: implied FDV, 80%
    interval, launch odds, expected value = FDV x p_launch, rank)
  - data/model_metrics.json (updated with round 2/3 numbers)
"""
import json
import math
from pathlib import Path

import numpy as np

from fit_model import load_rows, fold_of, fit_ols, metrics, irls, sigmoid
from fit_model2 import rank_metrics

DATA = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_TS = 1795400000
DAY = 86400
COHORT_CUT = 1704067200  # 2024-01-01 UTC


def design(rows, cats):
    X = []
    for r in rows:
        v = [1.0, math.log(r["tvl"])]
        # Map rare categories to OTHER here (not only in the caller): the
        # watchlist rows are not pre-mapped, and an unmapped category used
        # to fire NO dummy at all, silently dropping the OTHER effect.
        cat = r["category"] if r["category"] in cats else "OTHER"
        for c in cats:
            v.append(1.0 if cat == c else 0.0)
        v.append(math.log(max(r["chains"], 1)))
        age = max((SNAPSHOT_TS - (r["listedAt"] or SNAPSHOT_TS)) / DAY, 1.0)
        v.append(math.log(age))
        ch = r.get("change_7d")
        # DefiLlama change_7d is in PERCENT: divide by 100 (see fit_model.py).
        frac = (ch or 0.0) / 100.0 if ch is not None else 0.0
        v.append(math.log1p(max(frac, -0.99)))
        v.append(1.0 if (r["listedAt"] or 0) >= COHORT_CUT else 0.0)
        X.append(v)
    return np.array(X)


def main():
    rows = load_rows()
    cat_counts = {}
    for r in rows:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
    cats = sorted([c for c, n in cat_counts.items() if n >= 25]) + ["OTHER"]
    for r in rows:
        if r["category"] not in cats:
            r["category"] = "OTHER"
    filt = [r for r in rows if r["tvl"] >= 1e6 and r["fdv"] and r["fdv"] >= 1e5]
    y = np.array([math.log(r["fdv"]) for r in filt])
    X = design(filt, cats)
    beta = fit_ols(X, y)

    # split-conformal 80%/90% bands on one held-out fold
    folds = np.array([fold_of(r["key"]) for r in filt])
    cal = folds == 0
    beta_cal = fit_ols(X[~cal], y[~cal])
    resid = np.abs(y[cal] - X[cal] @ beta_cal)
    q80 = float(np.quantile(resid, 0.80))
    q90 = float(np.quantile(resid, 0.90))
    # in-sample fit quality (for the card; OOS numbers live in model_metrics)
    pred_all = X @ beta
    m_in = metrics(y, pred_all)
    print(f"final fit n={len(filt)} in-sample R2={m_in['r2']:.3f} "
          f"med ratio={m_in['median_ratio']:.2f}x")
    print(f"conformal q80={q80:.3f} (x{math.exp(q80):.2f}) q90={q90:.3f} (x{math.exp(q90):.2f})")
    print(f"log TVL slope={beta[1]:.3f} intercept={beta[0]:.3f} "
          f"cohort>=2024={beta[-1]:+.3f}")
    for c, b in zip(cats, beta[2:2 + len(cats)]):
        print(f"  cat {c:24s} {b:+.3f} (x{math.exp(b):.2f})")

    features = (["intercept", "log_tvl"] + [f"cat:{c}" for c in cats] +
                ["log_chains", "log_age_days", "log1p_change_7d", "listed_ge_2024"])
    json.dump({
        "target": "log_fdv", "snapshot": "2026-11-26",
        "training": "filtered comps: TVL>=1M, FDV>=100k, n=445",
        "features": features, "beta": [float(b) for b in beta],
        "conformal_q80_log": q80, "conformal_q90_log": q90,
        "cohort_cut_ts": COHORT_CUT, "snapshot_ts": SNAPSHOT_TS,
    }, open(DATA / "model_fdv.json", "w"), indent=1)

    # --- score the watchlist ----------------------------------------------
    # change_7d comes from the raw snapshot's flagship member (percent units;
    # design() scales it). The earlier version passed None here, which the
    # TS port then contradicted — caught by the TS/Python cross-check.
    raw = {p["slug"]: p for p in
           json.load(open(DATA / "protocols_raw_2026-11-26.json"))}
    watch = [f for f in json.load(open(DATA / "watchlist.json")) if f["tvl"] >= 5e4]
    launch = json.load(open(DATA / "model_launch.json"))
    lb = launch["beta"]
    lfeat_cats = [f.replace("cat:", "") for f in launch["features"] if f.startswith("cat:")]

    def launch_odds(f):
        # The odds model is trained on MATURE families (listed >= 1y): its
        # age coefficient partly measures "had time to launch". Scoring a
        # 1-month-old protocol at its true age would punish it for being
        # young, not for being unlikely to ever launch. So score at the
        # training floor: age = max(actual age, 365d) — the probability a
        # protocol with this TVL/category/chains has launched once mature.
        # Documented limitation: this is a mature-cohort launch probability,
        # not a time-to-launch forecast.
        age_d = max((SNAPSHOT_TS - (f["listedAt"] or SNAPSHOT_TS)) / DAY, 365.0)
        v = [1.0, math.log(f["tvl"]), math.log(age_d), math.log(max(f["chains"], 1))]
        cat = f["category"] if f["category"] in lfeat_cats else "OTHER"
        for c in lfeat_cats:
            v.append(1.0 if cat == c else 0.0)
        z = float(np.dot(np.array(v), np.array(lb)))
        return float(1.0 / (1.0 + math.exp(-max(min(z, 30), -30))))

    scored = []
    for f in watch:
        r = {"key": f["key"], "name": f["name"], "slug": f["slug"],
             "tvl": f["tvl"], "chains": max(f["chains"], 1),
             "category": f["category"], "listedAt": f["listedAt"],
             "change_7d": raw.get(f["slug"], {}).get("change_7d")}
        x = design([r], cats)[0]
        log_fdv = float(x @ beta)
        p = launch_odds(f)
        scored.append({
            **{k: f[k] for k in ("key", "name", "slug", "tvl", "chains",
                                 "category", "listedAt", "url", "twitter",
                                 "description")},
            "implied_fdv_usd": math.exp(log_fdv),
            "implied_fdv_lo80_usd": math.exp(log_fdv - q80),
            "implied_fdv_hi80_usd": math.exp(log_fdv + q80),
            "launch_probability": p,
            "expected_value_usd": math.exp(log_fdv) * p,
        })
    scored.sort(key=lambda s: -s["expected_value_usd"])
    for i, s in enumerate(scored, 1):
        s["rank"] = i
    json.dump(scored, open(DATA / "watchlist_scored.json", "w"), indent=1)
    print(f"\nwatchlist scored: {len(scored)} rows (TVL>=50k)")
    print("top 15 by expected value (implied FDV x launch probability):")
    for s in scored[:15]:
        print(f"  #{s['rank']:3d} {s['name']:32s} tvl=${s['tvl']/1e6:8.1f}M "
              f"implied=${s['implied_fdv_usd']/1e6:8.1f}M "
              f"[{s['implied_fdv_lo80_usd']/1e6:.1f}-{s['implied_fdv_hi80_usd']/1e6:.1f}]M "
              f"p_launch={s['launch_probability']:.2f} EV=${s['expected_value_usd']/1e6:.1f}M")
    print("top 10 by implied FDV alone:")
    for s in sorted(scored, key=lambda s: -s["implied_fdv_usd"])[:10]:
        print(f"  {s['name']:32s} implied=${s['implied_fdv_usd']/1e6:8.1f}M p={s['launch_probability']:.2f}")

    # update metrics file with the final numbers
    mm = json.load(open(DATA / "model_metrics.json"))
    mm["final_model"] = {
        "training": "filtered comps TVL>=1M, FDV>=100k, n=445",
        "features": features,
        "cv_median_ratio": 3.43, "cv_r2": 0.393, "cv_spearman": 0.62,
        "walkforward_train_le_2024_06": {
            "median_ratio": 3.20, "r2": 0.284, "bias_log": -0.22,
            "spearman": 0.59, "top_decile_overlap": 0.33,
            "top_decile_value_share": 0.61, "n_test": 153},
        "conformal_q80_log": q80, "conformal_q90_log": q90,
        "dropped": {
            "fees_30d": "CV 3.43x -> 3.61x, WF unchanged, top-decile overlap 40% -> 33%: no gain",
            "category_tvl_share": "collinear with category dummies + log TVL: identical metrics",
            "mcap_target": "CV 3.83x vs FDV 3.43x; WF R2 0.13 vs 0.28: FDV wins",
            "median_ratio_model": "CV 3.83x vs OLS 3.43x; WF R2 0.02 vs 0.28: OLS wins",
        },
    }
    json.dump(mm, open(DATA / "model_metrics.json", "w"), indent=1)
    print("\nsaved data/model_fdv.json, data/watchlist_scored.json, updated model_metrics.json")


if __name__ == "__main__":
    main()
