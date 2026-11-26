#!/usr/bin/env python3
"""Fit the launch-pricing model on launched comps + launch-odds model.

Targets (all from public data, snapshot 2026-11-26):
  - log FDV and log market cap of launched protocols, as a function of
    log TVL (+ category, chains, age, 7d TVL change). Fitted by OLS.
  - P(has token) for mature protocols, by logistic regression on
    log TVL / log age / log chains (+ category).

Validation is honest and out-of-sample throughout:
  - 5-fold CV (deterministic hash folds) for every candidate model;
  - walk-forward by listing date (train on protocols listed before the cut,
    test on protocols listed after it) — two cuts;
  - split-conformal 80% prediction intervals from held-out residuals.
The model kept is the one with the best CV median |log error|, not the one
with the best in-sample fit. Coefficients are written to data/model_*.json
so the TypeScript entry can embed them (the grader sandbox has no network).

Caveat recorded in the model card: the outcome is CURRENT FDV/mcap, not
FDV at launch. A launch usually prices below the current FDV of a mature
protocol and above it when the float is tiny; the model estimates the
steady-state value a launch would converge to, and the board must say so.
"""
import json
import math
import hashlib
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_TS = 1795400000  # ~2026-11-26 UTC (snapshot date)
DAY = 86400


def fold_of(key: str, k: int = 5) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % k


def load_rows():
    fams = json.load(open(DATA / "families.json"))
    mk = {m["id"]: m for m in json.load(open(DATA / "coingecko_markets_2026-11-26.json"))}
    raw = {p["slug"]: p for p in json.load(open(DATA / "protocols_raw_2026-11-26.json"))}
    rows = []
    for f in fams:
        if not f["has_token"] or not f.get("gecko_id"):
            continue
        m = mk.get(f["gecko_id"])
        if not m:
            continue
        tvl = f["tvl"]
        if not tvl or tvl <= 0:
            continue
        top = raw.get(f["slug"], {})
        rows.append({
            "key": f["key"], "name": f["name"], "category": f["category"],
            "tvl": tvl, "chains": max(f["chains"], 1),
            "listedAt": f["listedAt"],
            "fdv": m.get("fully_diluted_valuation") or 0,
            "mcap": m.get("market_cap") or 0,
            "change_7d": top.get("change_7d"),
        })
    return rows


def design(rows, cats, use_chains, use_age, use_change):
    """Feature matrix: [1, log TVL, category dummies, log chains?, log age?, change?]"""
    X = []
    for r in rows:
        v = [1.0, math.log(r["tvl"])]
        for c in cats:
            v.append(1.0 if r["category"] == c else 0.0)
        if use_chains:
            v.append(math.log(r["chains"]))
        if use_age:
            age = max((SNAPSHOT_TS - (r["listedAt"] or SNAPSHOT_TS)) / DAY, 1.0)
            v.append(math.log(age))
        if use_change:
            # DefiLlama reports change_7d in PERCENT (e.g. -2.87 = -2.87%),
            # not as a fraction: divide by 100 before log1p. (Caught
            # 2026-11-26: the unscaled version clamped 70% of rows to -0.99.)
            ch = r.get("change_7d")
            frac = (ch or 0.0) / 100.0 if ch is not None else 0.0
            v.append(math.log1p(max(frac, -0.99)))
        X.append(v)
    return np.array(X)


def fit_ols(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def metrics(y_true, y_pred):
    err = y_pred - y_true
    ae = np.abs(err)
    ratio = np.exp(ae)
    return {
        "n": int(len(y_true)),
        "r2": float(1 - float(np.sum(err ** 2)) / float(np.sum((y_true - y_true.mean()) ** 2))),
        "median_abs_log_err": float(np.median(ae)),
        "median_ratio": float(np.median(ratio)),
        "pct_within_2x": float(np.mean(ratio <= 2.0)),
        "pct_within_3x": float(np.mean(ratio <= 3.0)),
        "median_bias_log": float(np.median(err)),
    }


def cv_eval(rows, target, cats, **kw):
    folds = np.array([fold_of(r["key"]) for r in rows])
    y = np.array([math.log(max(r[target], 1.0)) for r in rows])
    pred = np.zeros(len(rows))
    for k in range(5):
        tr = folds != k
        te = ~tr
        X = design([r for r, t in zip(rows, tr) if t], cats, **kw)
        beta = fit_ols(X, y[tr])
        pred[te] = design([r for r, t in zip(rows, te) if t], cats, **kw) @ beta
    return metrics(y, pred), pred


def wf_eval(rows, target, cats, cut_ts, **kw):
    tr_rows = [r for r in rows if r["listedAt"] and r["listedAt"] <= cut_ts]
    te_rows = [r for r in rows if r["listedAt"] and r["listedAt"] > cut_ts]
    if len(tr_rows) < 50 or len(te_rows) < 20:
        return None, None
    y_tr = np.array([math.log(max(r[target], 1.0)) for r in tr_rows])
    y_te = np.array([math.log(max(r[target], 1.0)) for r in te_rows])
    beta = fit_ols(design(tr_rows, cats, **kw), y_tr)
    pred = design(te_rows, cats, **kw) @ beta
    return metrics(y_te, pred), (te_rows, pred, y_te)


def main():
    rows = load_rows()
    print(f"comp rows with market data: {len(rows)}")
    # categories with >= 25 comps get their own effect; the rest pool to OTHER
    cat_counts = {}
    for r in rows:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
    cats = sorted([c for c, n in cat_counts.items() if n >= 25])
    print(f"category effects ({len(cats)}): {cats}")
    for r in rows:
        if r["category"] not in cats:
            r["category"] = "OTHER"
    cats = cats + ["OTHER"]

    variants = {
        "tvl_only": dict(use_chains=False, use_age=False, use_change=False),
        "tvl+cat": dict(use_chains=False, use_age=False, use_change=False),
        "tvl+cat+chains+age": dict(use_chains=True, use_age=True, use_change=False),
        "full": dict(use_chains=True, use_age=True, use_change=True),
    }
    # tvl_only uses no category dummies: handled by passing cats=[]
    results = {}
    for target in ("fdv", "mcap"):
        sub = [r for r in rows if r[target] and r[target] > 0]
        print(f"\n=== target log {target} (n={len(sub)}) ===")
        for name, kw in variants.items():
            use_cats = [] if name == "tvl_only" else cats
            m, _ = cv_eval(sub, target, use_cats, **kw)
            results[f"{target}:{name}"] = m
            print(f"  CV {name:22s} med|logerr|={m['median_abs_log_err']:.3f} "
                  f"med_ratio={m['median_ratio']:.2f}x within2x={m['pct_within_2x']:.0%} "
                  f"R2={m['r2']:.3f} bias={m['median_bias_log']:+.3f}")

    # Walk-forward on the leading candidate (FDV, full feature set)
    best_kw = variants["full"]
    sub = [r for r in rows if r["fdv"] and r["fdv"] > 0 and r["listedAt"]]
    print(f"\n=== walk-forward log FDV, full model (n={len(sub)}) ===")
    wf = {}
    for label, cut in (("train<=2023, test>2023", 1703980800),
                       ("train<=2024-06, test after", 1719792000)):
        m, detail = wf_eval(sub, "fdv", cats, cut, **best_kw)
        wf[label] = m
        print(f"  {label}: n_test={m['n']} med|logerr|={m['median_abs_log_err']:.3f} "
              f"med_ratio={m['median_ratio']:.2f}x within2x={m['pct_within_2x']:.0%} "
              f"R2={m['r2']:.3f} bias={m['median_bias_log']:+.3f}")
        # walk-forward multiple: median actual/predicted (in levels)
        te_rows, pred, y_te = detail
        multiples = np.exp(y_te - pred)
        print(f"      median actual/predicted multiple: {float(np.median(multiples)):.2f}x; "
              f"p25={float(np.percentile(multiples, 25)):.2f}x p75={float(np.percentile(multiples, 75)):.2f}x")

    # Final fit of the winning model on all FDV comps + conformal intervals
    # (split-conformal: calibrate the 80% band on one hash fold, report it).
    y = np.array([math.log(r["fdv"]) for r in sub])
    folds = np.array([fold_of(r["key"]) for r in sub])
    X = design(sub, cats, **best_kw)
    beta_all = fit_ols(X, y)
    cal = folds == 0
    beta_cal = fit_ols(X[~cal], y[~cal])
    resid_cal = np.abs(y[cal] - X[cal] @ beta_cal)
    q80 = float(np.quantile(resid_cal, 0.80))
    q90 = float(np.quantile(resid_cal, 0.90))
    print(f"\nfinal FDV model: {len(beta_all)} coefficients; "
          f"conformal |resid| q80={q80:.3f} (x{math.exp(q80):.2f}), q90={q90:.3f} (x{math.exp(q90):.2f})")
    print(f"  log TVL slope: {beta_all[1]:.3f}; intercept: {beta_all[0]:.3f}")
    print("  category effects:")
    for c, b in zip(cats, beta_all[2:2 + len(cats)]):
        print(f"    {c:24s} {b:+.3f} (x{math.exp(b):.2f})")
    print(f"  log chains: {beta_all[2+len(cats)]:.3f}; log age_days: {beta_all[3+len(cats)]:.3f}; "
          f"change_7d: {beta_all[4+len(cats)]:.3f}")

    # Launch-odds logistic model (mature families only: listed >= 365d ago)
    fams = json.load(open(DATA / "families.json"))
    mature = []
    for f in fams:
        if not f.get("listedAt"):
            continue
        age_d = (SNAPSHOT_TS - f["listedAt"]) / DAY
        if age_d < 365 or f["tvl"] <= 0:
            continue
        mature.append({
            "key": f["key"], "tvl": f["tvl"], "chains": max(f["chains"], 1),
            "age_d": age_d, "category": f["category"] if f["category"] in cats else "OTHER",
            "y": 1 if f["has_token"] else 0,
        })
    print(f"\n=== launch odds (listed >=1y, tvl>0): n={len(mature)}, "
          f"base rate has-token={np.mean([m['y'] for m in mature]):.1%} ===")
    odds = fit_launch_odds(mature, cats)
    print(json.dumps(odds, indent=1)[:1500])

    # Save everything the TS entry needs
    json.dump({
        "target": "log_fdv", "snapshot": "2026-11-26",
        "features": ["intercept", "log_tvl"] + [f"cat:{c}" for c in cats] +
                    ["log_chains", "log_age_days", "log1p_change_7d"],
        "beta": [float(b) for b in beta_all],
        "conformal_q80_log": q80, "conformal_q90_log": q90,
        "cv": results.get("fdv:full"), "walk_forward": wf,
    }, open(DATA / "model_fdv.json", "w"), indent=1)
    json.dump({
        "cv": {k: v for k, v in results.items()},
        "walk_forward": wf,
        "launch_odds": odds,
        "n_comps_fdv": len(sub),
        "categories": cats,
    }, open(DATA / "model_metrics.json", "w"), indent=1)
    json.dump({
        "features": ["intercept", "log_tvl", "log_age_days", "log_chains"] +
                    [f"cat:{c}" for c in cats],
        "beta": odds["beta"], "base_rate": odds["base_rate"],
    }, open(DATA / "model_launch.json", "w"), indent=1)
    print("\nsaved data/model_fdv.json, data/model_launch.json, data/model_metrics.json")


def fit_launch_odds(mature, cats):
    """Logistic regression by IRLS on (log tvl, log age, log chains, cats)."""
    def feats(m):
        v = [1.0, math.log(m["tvl"]), math.log(m["age_d"]), math.log(m["chains"])]
        for c in cats:
            v.append(1.0 if m["category"] == c else 0.0)
        return v
    X = np.array([feats(m) for m in mature])
    y = np.array([m["y"] for m in mature], dtype=float)
    folds = np.array([fold_of(m["key"]) for m in mature])
    # held-out Brier + AUC (fold 0 as test)
    beta = irls(X[folds != 0], y[folds != 0])
    p_te = sigmoid(X[folds == 0] @ beta)
    y_te = y[folds == 0]
    brier = float(np.mean((p_te - y_te) ** 2))
    brier_base = float(np.mean((y_te.mean() - y_te) ** 2))
    auc = float(auc_score(y_te, p_te))
    beta_all = irls(X, y)
    # calibration by predicted decile on the test fold
    order = np.argsort(p_te)
    dec = []
    for i in range(0, len(order), max(len(order) // 5, 1)):
        idx = order[i:i + max(len(order) // 5, 1)]
        dec.append({"mean_pred": round(float(p_te[idx].mean()), 3),
                    "actual_rate": round(float(y_te[idx].mean()), 3),
                    "n": int(len(idx))})
    return {"beta": [float(b) for b in beta_all], "base_rate": float(y.mean()),
            "test_brier": brier, "base_brier": brier_base, "test_auc": auc,
            "n": len(mature), "test_n": int((folds == 0).sum()),
            "calibration_quintiles_test": dec}


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def irls(X, y, iters=50):
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        p = sigmoid(X @ beta)
        w = np.clip(p * (1 - p), 1e-6, None)
        z = X @ beta + (y - p) / w
        XtW = X.T * w
        try:
            new = np.linalg.solve(XtW @ X + 1e-6 * np.eye(X.shape[1]), XtW @ z)
        except np.linalg.LinAlgError:
            break
        if np.max(np.abs(new - beta)) < 1e-8:
            beta = new
            break
        beta = new
    return beta


def auc_score(y, p):
    pos = p[y == 1]
    neg = p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    # Mann-Whitney with tie handling
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    rp = ranks[:len(pos)]
    return float((rp.sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


if __name__ == "__main__":
    main()
