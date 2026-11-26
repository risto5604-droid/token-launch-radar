#!/usr/bin/env python3
"""Generate farm/launch plans for the token-radar board (Day 3, step 1).

Reads data/families.json + out/board.json (+ the raw snapshot for chain
names only) and writes data/farm_plans.json, keyed by family key.

Rules (FARM_PLAN.md):
- One template per category; steps are grounded ONLY in snapshot fields
  (chains, TVL tier, age, url/twitter, category). No invented facts.
- A points program may only be mentioned as "check the protocol's docs
  for a points program" -- the snapshot has no points field, so a plan
  never asserts one exists.
- Each plan carries its evidence: the snapshot fields each step used.
- Deterministic output: sorted keys, fixed ordering, no timestamps.

Category aliases (deviation from FARM_PLAN.md, recorded in
DAY3-NOTES.md): the board has 57 categories but the plan names 12
templates. Close kin map onto the named templates (Yield Aggregator ->
Yield, Onchain Capital Allocator -> Risk Curators, DEX Aggregator ->
Dexs, Liquid Restaking -> Liquid Staking, CDP Manager -> CDP, and the
bridge-family categories -> Bridge); everything else uses OTHER.
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
SNAPSHOT_TS = 1795400000  # 2026-11-26, same constant main.ts scores with

# category -> template id; anything unlisted falls through to OTHER.
ALIASES = {
    "Yield Aggregator": "Yield",
    "Onchain Capital Allocator": "Risk Curators",
    "DEX Aggregator": "Dexs",
    "Liquid Restaking": "Liquid Staking",
    "CDP Manager": "CDP",
    "Bridge Aggregator": "Bridge",
    "Bridge Aggregators": "Bridge",
    "Cross Chain Bridge": "Bridge",
    "Canonical Bridge": "Bridge",
}

# Each step: text with {placeholders} + the snapshot fields it is
# grounded in. Placeholders: name, chains (e.g. "Ethereum, Arbitrum"),
# chain_count, tvl (formatted), tvl_tier, age_days, category, url,
# twitter, fdv (formatted implied FDV), fdv_lo, fdv_hi, launch_p.
TEMPLATES = {
    "Risk Curators": [
        {
            "text": "Deposit into {name}'s vaults on {chains} ({chain_count} chains). "
                    "Curators allocate the capital you deposit, so your position is the "
                    "exposure -- size it to what you can leave untouched.",
            "evidence": ["chains", "tvl"],
        },
        {
            "text": "Stay deposited. {name} is {age_days} days old with {tvl} TVL "
                    "({tvl_tier}); curators and vault products reward sticky capital, "
                    "not deposits that arrive the week a launch is rumoured and leave.",
            "evidence": ["listedAt", "tvl"],
        },
        {
            "text": "Watch the official channels for new vaults and cap raises: {url} "
                    "and @{twitter}. New vaults open on official channels first; a "
                    "vault that is capped today may reopen without notice.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
        {
            "text": "Re-check the board after any large TVL move: the model prices "
                    "{name} at {fdv} implied FDV (80% interval {fdv_lo}--{fdv_hi}) "
                    "and the ranking moves with TVL.",
            "evidence": ["tvl", "impliedFdvUsd"],
        },
    ],
    "Lending": [
        {
            "text": "Supply assets to {name}'s lending markets on {chains} "
                    "({chain_count} chains). Supplying is the lowest-risk way to be a "
                    "user of a {tvl_tier} lender with {tvl} TVL.",
            "evidence": ["chains", "tvl"],
        },
        {
            "text": "If you borrow, keep a wide health factor: {name} is {age_days} "
                    "days old, and a liquidation during a volatile week ends the "
                    "position -- and any farming attached to it.",
            "evidence": ["listedAt"],
        },
        {
            "text": "Watch for new markets and collateral types on the official "
                    "channels: {url} and @{twitter}. New markets are where early "
                    "usage concentrates.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "Dexs": [
        {
            "text": "Provide liquidity in {name}'s pools on {chains} ({chain_count} "
                    "chains). A {tvl_tier} DEX with {tvl} TVL pays LPs from real "
                    "volume; pick pools you understand and watch impermanent loss.",
            "evidence": ["chains", "tvl"],
        },
        {
            "text": "Route trades through {name} when it is the best price on its "
                    "chains -- trading volume is the usage a DEX is judged on.",
            "evidence": ["chains"],
        },
        {
            "text": "Watch for new pools and incentives on the official channels: "
                    "{url} and @{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "Derivatives": [
        {
            "text": "Trade {name}'s derivatives on {chains} ({chain_count} chains) "
                    "with small size first. A {tvl_tier} derivatives venue with {tvl} "
                    "TVL rewards volume, but leverage punishes a first trade sized "
                    "like a tenth.",
            "evidence": ["chains", "tvl"],
        },
        {
            "text": "If {name} offers liquidity provision, consider it only after "
                    "you understand which side of the trade the LP takes -- the "
                    "snapshot says nothing about LP returns, so do not assume them.",
            "evidence": ["category"],
        },
        {
            "text": "Watch for new markets and fee changes on the official channels: "
                    "{url} and @{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "Yield": [
        {
            "text": "Deposit into {name}'s vaults or strategies on {chains} "
                    "({chain_count} chains). A {tvl_tier} yield product with {tvl} "
                    "TVL is where the yield comes from -- the vault, not a rumour.",
            "evidence": ["chains", "tvl"],
        },
        {
            "text": "Compare the yield across {name}'s chains and let it compound "
                    "rather than hopping weekly: {name} is {age_days} days old, and "
                    "the strategies that survive are the ones that compound.",
            "evidence": ["chains", "listedAt"],
        },
        {
            "text": "Watch for new strategies on the official channels: {url} and "
                    "@{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "RWA": [
        {
            "text": "Find which real-world assets {name} tokenizes and hold or mint "
                    "them on {chains} ({chain_count} chains). A {tvl_tier} RWA "
                    "protocol with {tvl} TVL is judged on the assets, not the wrapper.",
            "evidence": ["chains", "tvl", "category"],
        },
        {
            "text": "Read the asset documentation before minting: {name} is "
                    "{age_days} days old, and RWA value depends on the off-chain "
                    "asset and its custodian, which the snapshot does not describe.",
            "evidence": ["listedAt"],
        },
        {
            "text": "Watch for new asset listings on the official channels: {url} "
                    "and @{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "CDP": [
        {
            "text": "Mint {name}'s stablecoin against collateral on {chains} "
                    "({chain_count} chains). A {tvl_tier} CDP with {tvl} TVL is used "
                    "by minting, not by watching.",
            "evidence": ["chains", "tvl", "category"],
        },
        {
            "text": "Keep the collateral ratio wide: {name} is {age_days} days old, "
                    "and a liquidation ends the position. The snapshot records no "
                    "liquidation parameters, so read them in the docs before minting.",
            "evidence": ["listedAt", "url"],
        },
        {
            "text": "Watch for new collateral types on the official channels: {url} "
                    "and @{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "Farm": [
        {
            "text": "Stake LP tokens in {name}'s farms on {chains} ({chain_count} "
                    "chains). A {tvl_tier} farm with {tvl} TVL pays for staked "
                    "liquidity, not for idle tokens.",
            "evidence": ["chains", "tvl"],
        },
        {
            "text": "Harvest on a schedule rather than daily: {name} is {age_days} "
                    "days old, and on {chain_count} chains the gas cost of frequent "
                    "harvests eats the yield.",
            "evidence": ["listedAt", "chains"],
        },
        {
            "text": "Watch for new farms and emission changes on the official "
                    "channels: {url} and @{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "Launchpad": [
        {
            "text": "Check what {name} requires for allocations -- staking, holding "
                    "or whitelisting -- on {chains} ({chain_count} chains). A "
                    "{tvl_tier} launchpad with {tvl} TVL allocates to participants, "
                    "not spectators; the snapshot records no allocation rules, so "
                    "read them in the docs.",
            "evidence": ["chains", "tvl", "url"],
        },
        {
            "text": "Watch the official channels for upcoming launches: {url} and "
                    "@{twitter}. Launches are announced there first, and the window "
                    "to qualify is usually short.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "Bridge": [
        {
            "text": "Bridge assets through {name} across its {chain_count} chains "
                    "({chains}). A {tvl_tier} bridge with {tvl} TVL is used by "
                    "moving value, not by holding it.",
            "evidence": ["chains", "tvl"],
        },
        {
            "text": "Compare the fee and arrival time per route before bridging: "
                    "the snapshot records no fee schedule for {name}, so read it in "
                    "the docs at {url}.",
            "evidence": ["url"],
        },
        {
            "text": "Watch for newly supported chains on the official channels: "
                    "{url} and @{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "Liquid Staking": [
        {
            "text": "Stake through {name} on {chains} ({chain_count} chains) and "
                    "receive its liquid token. A {tvl_tier} liquid-staking protocol "
                    "with {tvl} TVL is used by staking, not by holding the "
                    "underlying idle.",
            "evidence": ["chains", "tvl"],
        },
        {
            "text": "Put the liquid token to work in DeFi on the same chains -- "
                    "that composability is the product. The snapshot records no "
                    "yields or integrations, so verify them in the docs at {url}.",
            "evidence": ["chains", "url"],
        },
        {
            "text": "Watch for new integrations on the official channels: {url} and "
                    "@{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
    "OTHER": [
        {
            "text": "Use {name}'s core product on {chains} ({chain_count} chains). "
                    "It is a {category} protocol with {tvl} TVL ({tvl_tier}) and "
                    "{age_days} days of history -- real usage is the position, "
                    "whatever the category.",
            "evidence": ["chains", "tvl", "category", "listedAt"],
        },
        {
            "text": "Read the docs before using it: {url}. The snapshot records no "
                    "product details for {name} beyond its category, TVL and chains, "
                    "so anything the docs do not say is not assumed here.",
            "evidence": ["url"],
        },
        {
            "text": "Watch the official channels for what changes next: {url} and "
                    "@{twitter}.",
            "evidence": ["url", "twitter"],
        },
        {
            "text": "Check the protocol's docs for a points program -- the snapshot "
                    "records no points program for {name}, so do not assume one exists.",
            "evidence": ["url"],
        },
    ],
}


def money(n: float) -> str:
    if n >= 1e9:
        return f"${n / 1e9:.2f}B"
    if n >= 1e6:
        return f"${n / 1e6:.1f}M"
    if n >= 1e3:
        return f"${n / 1e3:.0f}k"
    return f"${n:.0f}"


def tvl_tier(tvl: float) -> str:
    if tvl >= 1e9:
        return "mega"
    if tvl >= 1e8:
        return "large"
    if tvl >= 1e7:
        return "mid-size"
    if tvl >= 1e6:
        return "small"
    return "micro"


def main() -> None:
    board = json.load(open(HERE / "out" / "board.json"))
    families = {f["key"]: f for f in json.load(open(DATA / "families.json"))}
    # Chain names come from the raw snapshot (build-time input only);
    # families.json carries only the chain count.
    chain_names: dict[str, list[str]] = {}
    raw_path = DATA / "protocols_raw_2026-11-26.json"
    if raw_path.exists():
        raw = json.load(open(raw_path))
        by_slug = {p["slug"]: p for p in raw}
        for fam in families.values():
            names: set[str] = set()
            for slug in fam.get("member_slugs", []):
                p = by_slug.get(slug)
                if p:
                    names.update(p.get("chains") or [])
            chain_names[fam["key"]] = sorted(names)

    plans: dict[str, dict] = {}
    for row in board["rows"]:
        key = row["key"]
        fam = families.get(key, {})
        category = row["category"]
        template_id = category if category in TEMPLATES else ALIASES.get(category, "OTHER")
        template = TEMPLATES[template_id]
        listed_at = row.get("listedAt")
        age_days = (
            max(1, int((SNAPSHOT_TS - listed_at) / 86400)) if listed_at else None
        )
        names = chain_names.get(key) or []
        if names:
            chains_text = ", ".join(names)
        else:
            chains_text = f"{row['chains']} chains"
        ctx = {
            "name": row["name"],
            "chains": chains_text,
            "chain_count": row["chains"],
            "tvl": money(row["tvl"]),
            "tvl_tier": tvl_tier(row["tvl"]),
            "age_days": age_days if age_days is not None else "unknown age",
            "category": category,
            "url": fam.get("url") or row.get("url") or "the protocol's official site",
            "twitter": fam.get("twitter") or "the protocol's official account",
            "fdv": money(row["impliedFdvUsd"]),
            "fdv_lo": money(row["impliedFdvLo80Usd"]),
            "fdv_hi": money(row["impliedFdvHi80Usd"]),
        }
        steps = [
            {"text": s["text"].format(**ctx), "evidence": s["evidence"]}
            for s in template
        ]
        plans[key] = {
            "key": key,
            "name": row["name"],
            "rank": row["rank"],
            "category": category,
            "template": template_id,
            "tvl_tier": ctx["tvl_tier"],
            "age_days": age_days,
            "chains": names,
            "chain_count": row["chains"],
            "url": fam.get("url"),
            "twitter": fam.get("twitter"),
            "steps": steps,
        }

    out_path = DATA / "farm_plans.json"
    out_path.write_text(
        json.dumps(plans, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"farm_plans.json: {len(plans)} plans, "
          f"templates used: {sorted({p['template'] for p in plans.values()})}")


if __name__ == "__main__":
    main()
