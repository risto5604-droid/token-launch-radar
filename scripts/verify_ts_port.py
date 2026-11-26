#!/usr/bin/env python3
"""Verify the TypeScript CoinGecko cross-check port (Day 2).

Runs main.ts twice (with MAKEFUN_DEBUG_TOKEN_DETECT=1) and checks:
  1. determinism — both board.json runs byte-identical, and so is
     token_detect.json;
  2. family agreement — TS has_token matches data/families.json for all
     7,376 families, and the gecko_id matches too;
  3. review agreement — TS review items match data/token_match_review.json
     (same 279 keys);
  4. board agreement — the 739 scored rows match
     data/watchlist_scored.json: same keys in the same order, same top-3,
     numeric fields within 1e-9 relative tolerance.

Usage: python3 scripts/verify_ts_port.py
Exit code 0 when every check passes.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
TMP = Path("/tmp/tr-verify")
NODE = "node"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_main(out_dir):
    env = {
        "MAKEFUN_INPUT_DIR": "/tmp/tr-input",
        "MAKEFUN_OUTPUT_DIR": str(out_dir),
        "MAKEFUN_DEBUG_TOKEN_DETECT": "1",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }
    import os
    env.update({k: v for k, v in os.environ.items() if k not in env})
    env["MAKEFUN_INPUT_DIR"] = "/tmp/tr-input"
    env["MAKEFUN_OUTPUT_DIR"] = str(out_dir)
    env["MAKEFUN_DEBUG_TOKEN_DETECT"] = "1"
    r = subprocess.run([NODE, "main.ts"], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=300)
    return r


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


def main():
    ok = True
    for d in (TMP / "run1", TMP / "run2"):
        d.mkdir(parents=True, exist_ok=True)
    r1 = run_main(TMP / "run1")
    r2 = run_main(TMP / "run2")
    print("run1:", r1.stdout.strip().splitlines()[-1] if r1.stdout else r1.stderr[-500:])
    print("run2:", r2.stdout.strip().splitlines()[-1] if r2.stdout else r2.stderr[-500:])
    if r1.returncode != 0 or r2.returncode != 0:
        print("FAIL: main.ts exited non-zero")
        print(r1.stderr[-2000:], r2.stderr[-2000:])
        return 1

    # 1. determinism
    for f in ("board.json", "token_detect.json"):
        same = sha(TMP / "run1" / f) == sha(TMP / "run2" / f)
        print(f"determinism {f}: {'PASS' if same else 'FAIL'}")
        ok = ok and same

    ts = json.load(open(TMP / "run1" / "token_detect.json"))
    board = json.load(open(TMP / "run1" / "board.json"))
    py_fams = {f["key"]: f for f in json.load(open(DATA / "families.json"))}

    # 2. family agreement
    ts_map = {f["key"]: f for f in ts["families"]}
    print(f"families: python={len(py_fams)} ts={len(ts_map)}")
    if set(ts_map) != set(py_fams):
        print("FAIL: family key sets differ:",
              "only-ts:", sorted(set(ts_map) - set(py_fams))[:5],
              "only-py:", sorted(set(py_fams) - set(ts_map))[:5])
        ok = False
    mism_token, mism_gecko = [], []
    for k, pf in py_fams.items():
        tf = ts_map.get(k)
        if tf is None:
            continue
        if tf["hasToken"] != pf["has_token"]:
            mism_token.append((k, pf["name"], pf["has_token"], tf["hasToken"],
                               pf["gecko_evidence"]))
        if (tf["geckoId"] or None) != (pf["gecko_id"] or None):
            mism_gecko.append((k, pf["name"], pf["gecko_id"], tf["geckoId"]))
    print(f"has_token mismatches: {len(mism_token)}")
    for m in mism_token[:10]:
        print("  ", m)
    print(f"gecko_id mismatches: {len(mism_gecko)}")
    for m in mism_gecko[:10]:
        print("  ", m)
    ok = ok and not mism_token and not mism_gecko

    # 3. review agreement
    py_rev = json.load(open(DATA / "token_match_review.json"))
    py_keys = sorted(r["key"] for r in py_rev)
    ts_keys = sorted(r["key"] for r in ts["review"])
    print(f"review items: python={len(py_keys)} ts={len(ts_keys)}")
    if py_keys != ts_keys:
        print("FAIL: review key sets differ")
        print("  only-py:", sorted(set(py_keys) - set(ts_keys))[:10])
        print("  only-ts:", sorted(set(ts_keys) - set(py_keys))[:10])
        ok = False
    else:
        print("review keys: PASS")

    # 4. board agreement
    py_board = json.load(open(DATA / "watchlist_scored.json"))
    ts_rows = board["rows"]
    print(f"board rows: python={len(py_board)} ts={len(ts_rows)}")
    if len(py_board) != len(ts_rows):
        ok = False
    py_keys = [r["key"] for r in py_board]
    ts_keys = [r["key"] for r in ts_rows]
    order_ok = py_keys == ts_keys
    print(f"board row order identical: {'PASS' if order_ok else 'FAIL'}")
    if not order_ok:
        diff = [i for i, (a, b) in enumerate(zip(py_keys, ts_keys)) if a != b]
        print("  first order diffs at:", diff[:5])
        ok = False
    print("top-3 ts:", [(r["name"], round(r["expectedValueUsd"] / 1e6, 1))
                        for r in ts_rows[:3]])
    print("top-3 py:", [(r["name"], round(r["expected_value_usd"] / 1e6, 1))
                        for r in py_board[:3]])
    ts_fields = {"tvl": "tvl", "implied_fdv_usd": "impliedFdvUsd",
                 "implied_fdv_lo80_usd": "impliedFdvLo80Usd",
                 "implied_fdv_hi80_usd": "impliedFdvHi80Usd",
                 "launch_probability": "launchProbability",
                 "expected_value_usd": "expectedValueUsd"}
    worst = 0.0
    worst_at = None
    py_by_key = {r["key"]: r for r in py_board}
    for tr in ts_rows:
        pr = py_by_key.get(tr["key"])
        if pr is None:
            continue
        for pf, tf in ts_fields.items():
            d = rel(tr[tf], pr[pf])
            if d > worst:
                worst, worst_at = d, (tr["key"], pf, tr[tf], pr[pf])
    print(f"worst relative numeric diff: {worst:.3e} at {worst_at}")
    num_ok = worst < 1e-9
    print(f"numeric agreement (<1e-9 rel): {'PASS' if num_ok else 'FAIL'}")
    ok = ok and num_ok
    # If the order differs but the numbers agree, the swaps are float
    # noise between rows whose EVs are within rounding distance: show
    # the EV gap at each swapped position to confirm.
    if not order_ok and num_ok:
        print("order-diff EV gaps (ts row vs py row at same rank):")
        for i in sorted(set(
                [j for j, (a, b) in enumerate(zip(py_keys, ts_keys)) if a != b]))[:10]:
            tr, pr = ts_rows[i], py_by_key[ts_keys[i]]
            pr_at = py_by_key[py_keys[i]]
            print(f"  rank {i+1}: ts={tr['name']} EV={tr['expectedValueUsd']:.6f} "
                  f"py={pr_at['name']} EV={pr_at['expected_value_usd']:.6f} "
                  f"gap={abs(tr['expectedValueUsd']-pr_at['expected_value_usd']):.3e}")

    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
