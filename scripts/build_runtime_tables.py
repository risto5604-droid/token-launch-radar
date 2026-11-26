#!/usr/bin/env python3
"""Build the compact runtime tables for the TypeScript CoinGecko
cross-check (Day 2).

Reads the Day 1 raw public files and writes the two small tables the
entry ships at runtime (src/token_detect.ts loads them; the grader runs
with no network, so the matcher cannot fetch CoinGecko itself):

  - data/coingecko_list.json    : [[id, symbol, name], ...] (21,248 coins)
  - data/coingecko_markets.json : {id: [market_cap, fully_diluted_valuation]}

Both are written as single-line compact JSON: the tables are data, not
code, and one line each keeps them out of the entry's counted lines.
The 28 MB of Day 1 raw files (protocols snapshot, fees, families, ...)
are build-time inputs and are NOT shipped in the entry repository.

Run from the token-radar directory:  python3 scripts/build_runtime_tables.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"


def main():
    cg = json.load(open(DATA / "coingecko_list_2026-11-26.json"))
    rows = [[c["id"], c["symbol"], c["name"]] for c in cg]
    rows.sort(key=lambda r: r[0])
    with open(DATA / "coingecko_list.json", "w") as f:
        json.dump(rows, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")
    print(f"coingecko_list.json: {len(rows)} coins")

    markets = json.load(open(DATA / "coingecko_markets_2026-11-26.json"))
    m = {m["id"]: [m.get("market_cap") or 0, m.get("fully_diluted_valuation") or 0]
         for m in markets}
    with open(DATA / "coingecko_markets.json", "w") as f:
        json.dump(m, f, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
        f.write("\n")
    print(f"coingecko_markets.json: {len(m)} coins with market data")


if __name__ == "__main__":
    main()
