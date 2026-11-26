#!/usr/bin/env python3
"""Round 2: does the pricing model get better with (a) filtered comps
(dead-token tail removed), (b) a per-category median FDV/TVL ratio model
(slope fixed at 1), (c) a listing-cohort effect, (d) ranking metrics?

The question is not "does TVL predict FDV in-sample" but "can any simple
model rank launches out-of-sample well enough to be worth shipping".
Everything is scored on the same 5-fold CV + walk-forward splits as round 1.
"""
import json
import math
import hashlib
from pathlib import Path

import numpy as np

from fit_model import load_rows, fold_of, design, fit_ols, metrics, cv_eval, wf_eval

DATA = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_TS = 1795400000
DAY = 86400


def spearman(a, b):
    a = np.argsort(np.argsort(a))
    b = np.argsort(np.argsort(b))
    return float(np.corrcoef(a, b)[0, 1])


def rank_metrics(y_true_log, y_pred_log, top_frac=0.10):
    """Top-decile precision: share of actual top-decile value captured by
    the predicted top decile, and overlap of the top-decile sets."""
    y_true, y_pred = np.exp(y_true_log), np.exp(y_pred_log)
    k = max(int(len(y_true) * top_frac), 1)
    top_pred = set(np.argsort(-y_pred)[:k].tolist())
    top_true = set(np.argsort(-y_true)[:k].tolist())
    overlap = len(top_pred & top_true) / k
    value_share = float(y_true[list(top_pred)].sum() / y_true.sum())
    return {"spearman": spearman(y_true_log, y_pred_log),
            "top_decile_overlap": float(overlap),
            "top_decile_value_share": value_share}


def ratio_model_cv(rows, target):
    """Predicted log FDV = log TVL + median log(FDV/TVL) per category."""
    cats = sorted({r["category"] for r in rows})
    y = np.array([math.log(max(r[target], 1.0)) for r in rows])
    folds = np.array([fold_of(r["key"]) for r in rows])
    pred = np.zeros(len(rows))
    for k in range(5):
        tr, te = folds != k, folds == k
        med = {}
        for c in cats:
            vals = [math.log(max(r[target], 1.0)) - math.log(r["tvl"])
                    for r, t in zip(rows, tr) if t and r["category"] == c]
            med[c] = float(np.median(vals)) if vals else 0.0
        glob = float(np.median([math.log(max(r[target], 1.0)) - math.log(r["tvl"])
                                for r, t in zip(rows, tr) if t]))
        for i, (r, t) in enumerate(zip(rows, te)):
            if t:
                pred[i] = math.log(r["tvl"]) + med.get(r["category"], glob)
    return metrics(y, pred), pred, y


def ratio_model_wf(rows, target, cut_ts):
    cats = sorted({r["category"] for r in rows})
    tr = [r for r in rows if r["listedAt"] and r["listedAt"] <= cut_ts]
    te = [r for r in rows if r["listedAt"] and r["listedAt"] > cut_ts]
    med = {}
    for c in cats:
        vals = [math.log(max(r[target], 1.0)) - math.log(r["tvl"])
                for r in tr if r["category"] == c]
        med[c] = float(np.median(vals)) if vals else 0.0
    glob = float(np.median([math.log(max(r[target], 1.0)) - math.log(r["tvl"]) for r in tr]))
    y_te = np.array([math.log(max(r[target], 1.0)) for r in te])
    pred = np.array([math.log(r["tvl"]) + med.get(r["category"], glob) for r in te])
    return metrics(y_te, pred), pred, y_te


def main():
    rows = load_rows()
    cat_counts = {}
    for r in rows:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
    cats = sorted([c for c, n in cat_counts.items() if n >= 25]) + ["OTHER"]
    for r in rows:
        if r["category"] not in cats:
            r["category"] = "OTHER"

    variants = {
        "full": dict(use_chains=True, use_age=True, use_change=True),
    }
    print("=== A. all comps (n=1324) vs filtered comps (TVL>=1M, FDV>=100k) ===")
    filt = [r for r in rows if r["tvl"] >= 1e6 and r["fdv"] and r["fdv"] >= 1e5]
    print(f"filtered n={len(filt)}")
    for label, sub in (("all", [r for r in rows if r["fdv"] > 0]),
                       ("filtered", filt)):
        m, pred = cv_eval(sub, "fdv", cats, **variants["full"])
        y = np.array([math.log(r["fdv"]) for r in sub])
        rm = rank_metrics(y, pred)
        print(f"  OLS full [{label:9s}] med|logerr|={m['median_abs_log_err']:.3f} "
              f"ratio={m['median_ratio']:.2f}x R2={m['r2']:.3f} "
              f"spearman={rm['spearman']:.2f} top10overlap={rm['top_decile_overlap']:.0%} "
              f"top10valueshare={rm['top_decile_value_share']:.0%}")
        m2, pred2, y2 = ratio_model_cv(sub, "fdv")
        rm2 = rank_metrics(y2, pred2)
        print(f"  ratio model [{label:9s}] med|logerr|={m2['median_abs_log_err']:.3f} "
              f"ratio={m2['median_ratio']:.2f}x R2={m2['r2']:.3f} "
              f"spearman={rm2['spearman']:.2f} top10overlap={rm2['top_decile_overlap']:.0%} "
              f"top10valueshare={rm2['top_decile_value_share']:.0%}")

    print("\n=== B. walk-forward, filtered comps, both models ===")
    sub = [r for r in filt if r["listedAt"]]
    for label, cut in (("train<=2023", 1703980800), ("train<=2024-06", 1719792000)):
        m, detail = wf_eval(sub, "fdv", cats, cut, **variants["full"])
        te_rows, pred, y_te = detail
        rm = rank_metrics(y_te, pred)
        print(f"  OLS [{label}] n_test={m['n']} med_ratio={m['median_ratio']:.2f}x "
              f"R2={m['r2']:.3f} bias={m['median_bias_log']:+.2f} spearman={rm['spearman']:.2f} "
              f"top10overlap={rm['top_decile_overlap']:.0%}")
        m2, pred2, y2 = ratio_model_wf(sub, "fdv", cut)
        rm2 = rank_metrics(y2, pred2)
        print(f"  ratio [{label}] n_test={len(y2)} med_ratio={m2['median_ratio']:.2f}x "
              f"R2={m2['r2']:.3f} bias={m2['median_bias_log']:+.2f} spearman={rm2['spearman']:.2f} "
              f"top10overlap={rm2['top_decile_overlap']:.0%}")

    print("\n=== C. cohort effect: median log(FDV/TVL) by listing year (filtered) ===")
    for yr in range(2019, 2027):
        lo, hi = 1546300800 + (yr - 2019) * 31556952, 1546300800 + (yr - 2018) * 31556952
        sel = [r for r in filt if r["listedAt"] and lo <= r["listedAt"] < hi]
        if len(sel) >= 10:
            ratios = [math.log(r["fdv"]) - math.log(r["tvl"]) for r in sel]
            print(f"  listed {yr}: n={len(sel):4d} median log(FDV/TVL)={np.median(ratios):+.2f} "
                  f"(ratio {math.exp(np.median(ratios)):.2f}x)  median TVL=${np.median([r['tvl'] for r in sel])/1e6:.1f}M")

    print("\n=== D. within-category TVL rank vs FDV (filtered): is rank the signal? ===")
    # category TVL share: protocol TVL / category total TVL
    tot = {}
    for r in filt:
        tot[r["category"]] = tot.get(r["category"], 0) + r["tvl"]
    x = np.array([math.log(r["tvl"] / tot[r["category"]]) for r in filt])
    y = np.array([math.log(r["fdv"]) for r in filt])
    print(f"  corr(log category-share, log FDV) = {np.corrcoef(x, y)[0,1]:.3f}")
    print(f"  corr(log TVL, log FDV)            = {np.corrcoef([math.log(r['tvl']) for r in filt], y)[0,1]:.3f}")


if __name__ == "__main__":
    main()
