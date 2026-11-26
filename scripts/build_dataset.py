#!/usr/bin/env python3
"""Build the token-radar dataset from public sources (Day 1).

Sources (all public, no keys):
  - data/protocols_raw_2026-11-26.json : DefiLlama /api/competitions snapshot
    (GET https://api.llama.fi/protocols, 2026-11-26)
  - data/coingecko_list_2026-11-26.json : CoinGecko /coins/list, 2026-11-26
  - data/coingecko_markets_2026-11-26.json : CoinGecko /coins/markets
    (FDV/mcap; written by fetch_markets.py, optional at this stage)

Outputs (data/):
  - families.json      : every DefiLlama family (parentProtocol-grouped) with
                         token status, tvl, category, chains, age
  - watchlist.json     : pre-token families after exclusions (the radar board)
  - comps.json         : tokened families with TVL + FDV/mcap (calibration set)
  - token_match_review.json : matches that need a human eye

Token detection is evidence-based and conservative:
  1. any member's gecko_id (DefiLlama's own link), OR
  2. a CoinGecko coin whose SYMBOL matches a family symbol AND whose NAME
     scores >= 50 against the family names (exact name = 100, coin name a
     prefix of a family name = 50+len, token overlap only = 10). The best
     candidate wins only when its score is strictly above every other
     candidate (this kills lookalikes like "Legacy Morpho" vs "Morpho").
  3. NAME-ONLY matches (no symbol on the family, e.g. USDD, Bittensor dTAO)
     are recorded as PROVISIONAL and only confirmed when the coin shows up
     in CoinGecko markets data with market_cap > 0 (a real trading token).
     This blocks fake/unofficial coins such as CoinGecko's "Polymarket"
     (POLY), which is not Polymarket-the-company's token.
A family is never marked tokened on symbol alone (too many collisions).

Wrapped / staked-product exclusion (brief: "not a wrapped or staked product
of one that trades"): name/symbol patterns for staked|wrapped products, an
assetToken receipt token (WBETH, lsETH), whole-category exclusions for
CEX / Bridge / Canonical Bridge, and Liquid Staking / Liquid Restaking
receipt-token products (their product IS a staked asset; a governance token
is a separate question and those families are tokened-or-excluded anyway).
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_DATE = "2026-11-26"

EXCLUDED_CATEGORIES = {"CEX", "Bridge", "Canonical Bridge"}
RECEIPT_CATEGORIES = {"Liquid Staking", "Liquid Restaking"}

# Manual token overrides: families the automatic matcher cannot prove, each
# verified against a public source (see the evidence string). Key = family key.
MANUAL_OVERRIDES = {
    # M0: docs.m0.org/protocol/roles — POWER and ZERO are live governance
    # tokens (POWER votes on minters/validators/rates; ZERO claims revenue).
    # Neither is listed on CoinGecko, so no gecko_id / no FDV for comps.
    "m0": (None, "manual: M0 docs — POWER/ZERO governance tokens exist"),
    # Cooler Loans is Olympus DAO's lending product (symbol OHM on the
    # DefiLlama entry); its token is OHM (CoinGecko 'olympus').
    "cooler-loans": ("olympus", "manual: Olympus DAO product, token OHM"),
    # Saphyre V3 is DragonSwap's concentrated-liquidity product on Sei
    # (symbol DRG); its token is DRG (CoinGecko 'dragonswap', mcap $2.75M).
    "saphyre-v3": ("dragonswap", "manual: DragonSwap product, token DRG"),
    # MUX Perps is MUX Protocol's perp product (symbol MCB); its token is
    # MCB (CoinGecko 'mcdex', mcap $7.8M).
    "mux-perps": ("mcdex", "manual: MUX Protocol product, token MCB"),
}

WRAPPED_SYMBOL_RE = re.compile(
    r"^(wst|st|s|w|x|ls)?(eth|btc|sol|trx|bnb|avax|matic|usdt|usdc|dai)$", re.I
)
STAKED_NAME_RE = re.compile(r"\bstaked\b|\bwrapped\b", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tokens(s: str) -> set:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) >= 3}


def score_coin(fam_names, coin_name):
    """Score a CoinGecko coin against family names. Higher = stronger.

    exact name equality: 100; coin name a prefix of a family name: 50+len;
    family name a prefix of the coin name: 40; shared content-token overlap: 10.
    0 when there is no real evidence (symbol alone never matches).
    """
    cn = norm(coin_name)
    if len(cn) < 3:
        return 0
    ct = tokens(coin_name)
    best = 0
    for fn in fam_names:
        fnn = norm(fn)
        if not fnn or len(fnn) < 3:
            continue
        if cn == fnn:
            return 100
        if fnn.startswith(cn):
            best = max(best, 50 + len(cn))
        elif cn.startswith(fnn):
            best = max(best, 40)
        ft = tokens(fn)
        if ct and ft:
            inter = {t for t in ct & ft if len(t) >= 4}
            if inter and len(inter) / max(len(ct), len(ft)) >= 0.34:
                best = max(best, 10 * len(inter))
            # first content token identical (e.g. "Curve" in "Curve DAO Token"
            # vs "Curve DEX"): the protocol's own name, versioned differently.
            first_ct = sorted(ct, key=lambda t: coin_name.lower().find(t))
            first_ft = sorted(ft, key=lambda t: fn.lower().find(t))
            if first_ct and first_ft and first_ct[0] == first_ft[0] \
                    and len(first_ct[0]) >= 5:
                best = max(best, 50)
            # first-token prefix either way ("solvbtc" vs "solv", "realt" vs
            # "realtoken"): a product/child named after its parent protocol.
            if first_ct and first_ft:
                a, b = first_ct[0], first_ft[0]
                if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
                    best = max(best, 60)
    return best


def best_coin_match(fam_names, candidates, min_score=50, live_mcap=None):
    """Return (coin, score) iff one candidate is strictly best with score>=min.

    A tie at the top score is broken by live market cap (a real, valuable
    token is far likelier to be the protocol's token than a same-name
    microcap: 'aerodrome-finance' vs 'aero', 'dydx-chain' vs 'dydx-wormhole',
    'dodo' vs 'dodo-2'). Only when mcap cannot break the tie is it ambiguous.
    """
    live_mcap = live_mcap or {}
    scored = [(c, score_coin(fam_names, c["name"])) for c in candidates]
    scored = [(c, s) for c, s in scored if s >= min_score]
    if not scored:
        return None, 0
    scored.sort(key=lambda cs: -cs[1])
    if len(scored) > 1 and scored[0][1] == scored[1][1]:
        top = [cs for cs in scored if cs[1] == scored[0][1]]
        top.sort(key=lambda cs: -live_mcap.get(cs[0]["id"], 0))
        if len(top) > 1 and live_mcap.get(top[0][0]["id"], 0) > live_mcap.get(top[1][0]["id"], 0):
            return top[0]
        return None, scored[0][1]  # tie -> ambiguous, needs review
    return scored[0]


def main():
    protos = json.load(open(DATA / "protocols_raw_2026-11-26.json"))
    cg = json.load(open(DATA / "coingecko_list_2026-11-26.json"))
    by_symbol = defaultdict(list)
    by_name = defaultdict(list)
    for c in cg:
        by_symbol[c["symbol"].lower()].append(c)
        by_name[norm(c["name"])].append(c)
    # market-cap confirmation for provisional (name-only) matches
    markets_file = DATA / "coingecko_markets_2026-11-26.json"
    live_mcap = {}
    live_fdv = {}
    if markets_file.exists():
        for m in json.load(open(markets_file)):
            live_mcap[m["id"]] = m.get("market_cap") or 0
            live_fdv[m["id"]] = m.get("fully_diluted_valuation") or 0

    fam = defaultdict(list)
    for p in protos:
        fam[p.get("parentProtocol") or p["slug"]].append(p)

    families = []
    review = []
    for key, members in fam.items():
        members = sorted(members, key=lambda m: -(m.get("tvl") or 0))
        top = members[0]
        tvl = sum((m.get("tvl") or 0) for m in members
                  if not m.get("excludeTvlFromParent"))
        chains = set()
        for m in members:
            chains.update(m.get("chains") or [])
        cats = Counter(m.get("category") for m in members if m.get("category"))
        cat = cats.most_common(1)[0][0] if cats else None
        listed = [m["listedAt"] for m in members if m.get("listedAt")]
        symbols = {m.get("symbol") for m in members if m.get("symbol") not in (None, "-", "")}
        geckos = {m["gecko_id"] for m in members if m.get("gecko_id")}
        mcaps = [m["mcap"] for m in members if m.get("mcap")]
        names = [m["name"] for m in members]
        # Name matching scores ONLY the flagship product (top member) and the
        # parent slug: a stray minor member ("Stellar DeFi Hub" grouped under
        # Sentora) must never mark the whole family tokened.
        score_names = [top["name"]]
        if key.startswith("parent#"):
            score_names.append(key[len("parent#"):].replace("-", " "))
        asset_tokens = {m.get("assetToken") for m in members if m.get("assetToken")}

        # --- token detection -------------------------------------------------
        matched_coin = None
        match_evidence = []
        provisional = False
        has_token_override = False
        if key in MANUAL_OVERRIDES:
            matched_coin, ev = MANUAL_OVERRIDES[key]
            match_evidence.append(ev)
            has_token_override = True
        elif geckos:
            matched_coin = sorted(geckos)[0]
            match_evidence.append("defillama gecko_id")
            has_token_override = False
        else:
            # (a) symbol-anchored candidates
            cands = {}
            for sym in symbols:
                for coin in by_symbol.get(sym.lower(), []):
                    cands.setdefault(coin["id"], coin)
            coin, score = best_coin_match(score_names, list(cands.values()),
                                          min_score=40, live_mcap=live_mcap)
            if coin:
                matched_coin = coin["id"]
                match_evidence.append(
                    f"coingecko symbol+name match: {coin['name']} (score {score})")
            elif len(cands) == 1:
                # Exactly one CoinGecko coin carries this symbol and the
                # family name contains the symbol as a word ("VVS Standard"
                # vs VVS Finance, "MUX Perps" vs MUX Protocol, "Abracadabra
                # Spell" vs Spell): that is the protocol's token.
                only = next(iter(cands.values()))
                fam_words = set()
                for fn in score_names:
                    fam_words.update(tokens(fn))
                if only["symbol"].lower() in {w.lower() for w in fam_words}:
                    matched_coin = only["id"]
                    match_evidence.append(
                        f"coingecko single-symbol match: {only['name']}")
            if not matched_coin:
                # (b) name-only: exact name equality, or coin name a strict
                # prefix (>=6 chars) of a family name. Provisional until the
                # coin is confirmed trading (markets data, mcap > 0).
                name_cands = {}
                for fn in score_names:
                    fnn = norm(fn)
                    for coin in by_name.get(fnn, []):
                        name_cands.setdefault(coin["id"], coin)
                    # coin name a strict prefix (>=6 chars) of a family name:
                    # generate the family name's prefixes and look them up.
                    for L in range(6, len(fnn)):
                        for coin in by_name.get(fnn[:L], []):
                            name_cands.setdefault(coin["id"], coin)
                coin, score = best_coin_match(score_names, list(name_cands.values()),
                                              live_mcap=live_mcap)
                if coin:
                    # Confirmed trading = CoinGecko markets quotes it: a
                    # market cap, or an FDV (a live price with no circulating
                    # supply reported yet, e.g. BinaryX/BNX). A coin with
                    # neither (Polymarket/POLY, Extended/XTEN pre-claim,
                    # Curvance/CVE) is NOT a trading token.
                    if live_mcap.get(coin["id"], 0) > 0 or live_fdv.get(coin["id"], 0) > 0:
                        matched_coin = coin["id"]
                        match_evidence.append(
                            f"coingecko name-only match, confirmed trading: "
                            f"{coin['name']} (score {score}, mcap "
                            f"${live_mcap[coin['id']]:,.0f})")
                    else:
                        provisional = True
                        review.append({
                            "family": top["name"], "key": key,
                            "symbols": sorted(symbols),
                            "candidate": {"id": coin["id"], "name": coin["name"],
                                        "symbol": coin["symbol"]},
                            "score": score, "tvl": tvl,
                            "reason": "name-only match, NOT confirmed trading "
                                      "(no markets mcap) - verify manually",
                        })
                elif cands:
                    review.append({
                        "family": top["name"], "key": key,
                        "symbols": sorted(symbols),
                        "candidates": [{"id": c["id"], "name": c["name"],
                                        "symbol": c["symbol"],
                                        "score": score_coin(score_names, c["name"])}
                                       for c in cands.values()],
                        "tvl": tvl,
                        "reason": "symbol-anchored candidates but no clear winner",
                    })

        # --- wrapped / staked product detection ------------------------------
        wrapped = False
        wrap_why = []
        if any(STAKED_NAME_RE.search(n) for n in names):
            wrapped = True
            wrap_why.append("name contains staked/wrapped")
        if any(WRAPPED_SYMBOL_RE.match(s or "") for s in symbols):
            wrapped = True
            wrap_why.append("symbol looks like wrapped/staked asset")
        if asset_tokens:
            wrapped = True
            wrap_why.append(f"receipt assetToken: {sorted(asset_tokens)}")
        if cat in RECEIPT_CATEGORIES:
            wrapped = True
            wrap_why.append(f"category {cat}: receipt-token product")

        families.append({
            "key": key,
            "name": top["name"],
            "slug": top["slug"],
            "member_slugs": [m["slug"] for m in members],
            "members": len(members),
            "tvl": tvl,
            "chains": len(chains),
            "category": cat,
            "listedAt": min(listed) if listed else None,
            "symbols": sorted(symbols),
            "gecko_id": matched_coin,
            "gecko_evidence": match_evidence,
            "provisional_token_match": provisional,
            "defillama_mcap": max(mcaps) if mcaps else None,
            "has_token": matched_coin is not None or has_token_override,
            "wrapped_or_staked": wrapped,
            "wrap_why": wrap_why,
            "excluded_category": cat in EXCLUDED_CATEGORIES,
            "url": top.get("url"),
            "twitter": top.get("twitter"),
            "description": (top.get("description") or "")[:400],
        })

    families.sort(key=lambda f: -f["tvl"])
    json.dump(families, open(DATA / "families.json", "w"), indent=1)
    json.dump(review, open(DATA / "token_match_review.json", "w"), indent=1)

    watch = [f for f in families
             if not f["has_token"]
             and not f["wrapped_or_staked"]
             and not f["excluded_category"]
             and f["tvl"] > 0]
    json.dump(watch, open(DATA / "watchlist.json", "w"), indent=1)

    comps = [f for f in families if f["has_token"] and f["tvl"] > 0]
    json.dump(comps, open(DATA / "comps.json", "w"), indent=1)

    print(f"families: {len(families)}")
    print(f"tokened families: {sum(1 for f in families if f['has_token'])}")
    n_cg = sum(1 for f in families if f["has_token"] and f["gecko_evidence"]
               and "coingecko" in f["gecko_evidence"][0])
    print(f"  of which via coingecko match: {n_cg}")
    print(f"review items: {len(review)}")
    print(f"wrapped/staked flagged: {sum(1 for f in families if f['wrapped_or_staked'])}")
    print(f"excluded-category: {sum(1 for f in families if f['excluded_category'])}")
    print(f"watchlist tvl>0: {len(watch)}")
    for th in (1e5, 1e6, 1e7, 1e8):
        print(f"  watchlist tvl>{th/1e6:g}M: {sum(1 for f in watch if f['tvl'] > th)}")
    print(f"comps tvl>0: {len(comps)}")
    print("watchlist top 15:")
    for f in watch[:15]:
        print(f"  {f['name']:34s} tvl={f['tvl']/1e6:9.1f}M cat={f['category']} chains={f['chains']} listedAt={f['listedAt']}")
    print("watchlist categories (tvl>1M):")
    print(Counter(f["category"] for f in watch if f["tvl"] > 1e6).most_common(20))


if __name__ == "__main__":
    main()
