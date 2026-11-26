#!/usr/bin/env python3
"""Fetch CoinGecko /coins/markets (FDV + market cap) for every candidate token.

IDs come from families.json (matched gecko_ids) + token_match_review.json
(provisional candidates) + a few explicit checks (polymarket). Public
endpoint, no key; batched 200 ids/call with a pause to stay inside the free
rate limit. Output: data/coingecko_markets_2026-11-26.json
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
URL = "https://api.coingecko.com/api/v3/coins/markets"


def fetch(ids):
    qs = urllib.parse.urlencode({
        "vs_currency": "usd",
        "ids": ",".join(ids),
        "per_page": 250,
        "page": 1,
        "price_change_percentage": "1y",
    })
    req = urllib.request.Request(URL + "?" + qs, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main():
    ids = set()
    fams = json.load(open(DATA / "families.json"))
    for f in fams:
        if f.get("gecko_id"):
            ids.add(f["gecko_id"])
    review = json.load(open(DATA / "token_match_review.json"))
    for r in review:
        if "candidate" in r:
            ids.add(r["candidate"]["id"])
        for c in r.get("candidates", []):
            ids.add(c["id"])
    ids.add("polymarket")  # explicit check: is CG's POLY a real trading token?
    ids = sorted(ids)
    print(f"{len(ids)} ids to fetch")
    out = []
    batch = 200
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        try:
            rows = fetch(chunk)
        except Exception as e:
            print(f"batch {i//batch} failed: {e}; retrying once after 30s")
            time.sleep(30)
            rows = fetch(chunk)
        out.extend(rows)
        print(f"batch {i//batch}: {len(rows)} rows (total {len(out)})")
        time.sleep(4)
    json.dump(out, open(DATA / "coingecko_markets_2026-11-26.json", "w"), indent=1)
    have_fdv = sum(1 for r in out if r.get("fully_diluted_valuation"))
    have_mcap = sum(1 for r in out if r.get("market_cap"))
    print(f"rows: {len(out)}, with FDV: {have_fdv}, with mcap: {have_mcap}")
    poly = [r for r in out if r["id"] == "polymarket"]
    print("polymarket row:", poly)


if __name__ == "__main__":
    main()
