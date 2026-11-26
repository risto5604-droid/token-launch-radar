#!/usr/bin/env python3
"""Round 3: cohort dummy + category-share feature + big-protocol evaluation.

Candidates are scored on filtered comps (TVL>=1M, FDV>=100k) with the same
5-fold CV and walk-forward splits. The winner is refit on all filtered
comps and shipped; the loser is dropped (blind-test discipline).
"""
import json
import math
from pathlib import Path

import numpy as np

from fit_model import load_rows, fold_of, fit_ols, metrics
from fit_model2 import rank_metrics

DATA = Path(__file__).resolve().parent.parent / "data"


def design3(rows, cats, cat_totals, cohort=True, share=True):
    X = []
    for r in rows:
        v = [1.0, math.log(r["tvl"])]
        for c in cats:
            v.append(1.0 if r["category"] == c else 0.0)
        v.append(math.log(r["chains"]))
        age = max((1795400000 - (r["listedAt"] or 1795400000)) / 86400, 1.0)
        v.append(math.log(age))
        ch = r.get("change_7d")
        # DefiLlama change_7d is in PERCENT: divide by 100 (see fit_model.py).
        frac = (ch or 0.0) / 100.0 if ch is not None else 0.0
        v.append(math.log1p(max(frac, -0.99)))
        if cohort:
            v.append(1.0 if (r["listedAt"] or 0) >= 1704067200 else 0.0)  # listed >= 2024
        if share:
            tot = cat_totals.get(r["category"], r["tvl"])
            v.append(math.log(max(r["tvl"] / tot, 1e-9)))
        X.append(v)
    return np.array(X)


def eval_variant(rows, cats, target, cohort, share, tvl_min_test=None):
    cat_totals = {}
    for r in rows:
        cat_totals[r["category"]] = cat_totals.get(r["category"], 0) + r["tvl"]
    y = np.array([math.log(max(r[target], 1.0)) for r in rows])
    folds = np.array([fold_of(r["key"]) for r in rows])
    pred = np.zeros(len(rows))
    for k in range(5):
        tr, te = folds != k, folds == k
        X = design3([r for r, t in zip(rows, tr) if t], cats, cat_totals, cohort, share)
        beta = fit_ols(X, y[tr])
        pred[te] = design3([r for r, t in zip(rows, te) if t], cats, cat_totals, cohort, share) @ beta
    m = metrics(y, pred)
    rm = rank_metrics(y, pred)
    # walk-forward (train<=2024-06)
    tr_rows = [r for r in rows if r["listedAt"] and r["listedAt"] <= 1719792000]
    te_rows = [r for r in rows if r["listedAt"] and r["listedAt"] > 1719792000]
    if tvl_min_test:
        te_rows = [r for r in te_rows if r["tvl"] >= tvl_min_test]
    y_tr = np.array([math.log(max(r[target], 1.0)) for r in tr_rows])
    y_te = np.array([math.log(max(r[target], 1.0)) for r in te_rows])
    beta = fit_ols(design3(tr_rows, cats, cat_totals, cohort, share), y_tr)
    pred_wf = design3(te_rows, cats, cat_totals, cohort, share) @ beta
    mw = metrics(y_te, pred_wf)
    rmw = rank_metrics(y_te, pred_wf)
    return m, rm, mw, rmw, len(te_rows)


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
    filt_mcap = [r for r in rows if r["tvl"] >= 1e6 and r["mcap"] and r["mcap"] >= 1e5]
    print(f"filtered FDV n={len(filt)}, filtered mcap n={len(filt_mcap)}")
    for label, sub, target in (("FDV", filt, "fdv"), ("MCAP", filt_mcap, "mcap")):
        for cohort, share in ((False, False), (True, False), (False, True), (True, True)):
            m, rm, mw, rmw, nte = eval_variant(sub, cats, target, cohort, share)
            print(f"  {label} cohort={int(cohort)} share={int(share)}: "
                  f"CV ratio={m['median_ratio']:.2f}x R2={m['r2']:.3f} spear={rm['spearman']:.2f} | "
                  f"WF ratio={mw['median_ratio']:.2f}x R2={mw['r2']:.3f} bias={mw['median_bias_log']:+.2f} "
                  f"spear={rmw['spearman']:.2f} top10={rmw['top_decile_overlap']:.0%} (n_test={nte})")
    print("\n=== same winner, evaluated only on big test protocols (TVL>=10M) ===")
    for cohort, share in ((False, False), (True, True)):
        m, rm, mw, rmw, nte = eval_variant(filt, cats, "fdv", cohort, share, tvl_min_test=1e7)
        print(f"  FDV cohort={int(cohort)} share={int(share)} TVL>=10M test: "
              f"WF ratio={mw['median_ratio']:.2f}x R2={mw['r2']:.3f} bias={mw['median_bias_log']:+.2f} "
              f"spear={rmw['spearman']:.2f} top10={rmw['top_decile_overlap']:.0%} (n_test={nte})")


if __name__ == "__main__":
    main()
