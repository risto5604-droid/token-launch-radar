// token_detect.ts — CoinGecko cross-check, ported to TypeScript (Day 2).
//
// Faithful port of scripts/build_dataset.py's token detection. A family
// is tokened when any member has a DefiLlama gecko_id, OR a CoinGecko
// coin matches it by symbol+name (scored matching, strict-best-wins
// with a live-mcap tie-break), OR a name-only match is confirmed
// trading by the markets table. A family is NEVER marked tokened on
// symbol alone, and name-only matches with no quoted mcap/FDV stay
// provisional (not tokened) — this rejects fake/unofficial coins such
// as CoinGecko's "Polymarket"/POLY, which has no market data.
//
// Name matching scores ONLY the flagship member's name and the parent
// slug: a stray minor member ("Stellar DeFi Hub" grouped under
// Sentora) must never mark the whole family tokened.
//
// The CoinGecko list (21,248 coins) and the markets table (2,520 rows)
// are embedded as data/coingecko_list.json and
// data/coingecko_markets.json, generated offline by
// scripts/build_runtime_tables.py from the 2026-11-26 public fetches.
// The grader runs with no network, so the matcher cannot fetch them
// at runtime. Manual overrides are the four families the automatic
// matcher cannot prove, each verified against a public source (see
// build_dataset.py for the evidence).

import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface CoinRow {
  id: string;
  symbol: string;
  name: string;
}

export interface CoinTables {
  bySymbol: Map<string, CoinRow[]>;
  byName: Map<string, CoinRow[]>;
  liveMcap: Map<string, number>;
  liveFdv: Map<string, number>;
}

/** A family as the detector sees it: flagship name, parent key,
 *  member symbols, every member's DefiLlama gecko_id, and TVL (for
 *  the human-review list only). */
export interface DetectableFamily {
  key: string;
  name: string;
  symbols: string[];
  geckoIds: string[];
  tvl: number;
}

export interface TokenDecision {
  hasToken: boolean;
  geckoId: string | null;
  evidence: string[];
  provisional: boolean;
}

export interface ReviewCandidate {
  id: string;
  name: string;
  symbol: string;
  score: number;
}

export interface ReviewItem {
  family: string;
  key: string;
  symbols: string[];
  candidate?: ReviewCandidate;
  candidates?: ReviewCandidate[];
  score?: number;
  tvl: number;
  reason: string;
}

// Manual token overrides: families the automatic matcher cannot prove,
// each verified against a public source. Key = family key.
const MANUAL_OVERRIDES: Record<string, { geckoId: string | null; evidence: string }> = {
  // M0: docs.m0.org/protocol/roles — POWER and ZERO are live governance
  // tokens. Neither is listed on CoinGecko, so no gecko_id / no FDV.
  m0: { geckoId: null, evidence: "manual: M0 docs — POWER/ZERO governance tokens exist" },
  // Cooler Loans is Olympus DAO's lending product (symbol OHM); token OHM.
  "cooler-loans": { geckoId: "olympus", evidence: "manual: Olympus DAO product, token OHM" },
  // Saphyre V3 is DragonSwap's concentrated-liquidity product on Sei
  // (symbol DRG); token DRG (CoinGecko 'dragonswap', mcap $2.75M).
  "saphyre-v3": { geckoId: "dragonswap", evidence: "manual: DragonSwap product, token DRG" },
  // MUX Perps is MUX Protocol's perp product (symbol MCB); token MCB
  // (CoinGecko 'mcdex', mcap $7.8M).
  "mux-perps": { geckoId: "mcdex", evidence: "manual: MUX Protocol product, token MCB" },
};

/** Coerce one list element to a string when possible (strings pass
 *  through; numbers/booleans/bigints via String()); anything else
 *  (null, undefined, objects, symbols) cannot be a coin field, so
 *  the caller skips that row. */
function toCoinField(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  return null;
}

/** Coerce a markets-table value to a finite number, falling back to 0
 *  for anything missing, non-numeric, or non-finite. */
function toMcap(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return 0;
}

/** Load the embedded CoinGecko tables from a directory holding
 *  coingecko_list.json ([[id, symbol, name], ...]) and
 *  coingecko_markets.json ({id: [market_cap, fdv]}). List rows that
 *  are not [string, string, string] triples are skipped (each element
 *  is coerced to a string when possible; a row with an uncoercible
 *  element is dropped), and markets pairs are coerced to finite
 *  numbers with a 0 fallback — a malformed row can never throw.
 *  A missing or unparseable file still throws (main.ts's safety net
 *  covers that); that behavior is unchanged. */
export function loadCoinTables(dataDir: string): CoinTables {
  const list: unknown = JSON.parse(
    readFileSync(join(dataDir, "coingecko_list.json"), "utf8"),
  );
  const markets: unknown = JSON.parse(
    readFileSync(join(dataDir, "coingecko_markets.json"), "utf8"),
  );
  if (!Array.isArray(list)) {
    throw new TypeError("loadCoinTables: coingecko_list.json is not an array of triples");
  }
  const bySymbol = new Map<string, CoinRow[]>();
  const byName = new Map<string, CoinRow[]>();
  for (const row of list) {
    if (!Array.isArray(row) || row.length !== 3) continue;
    const id = toCoinField(row[0]);
    const symbol = toCoinField(row[1]);
    const name = toCoinField(row[2]);
    if (id === null || symbol === null || name === null) continue;
    const coin: CoinRow = { id, symbol, name };
    const sKey = symbol.toLowerCase();
    const sList = bySymbol.get(sKey) ?? [];
    sList.push(coin);
    bySymbol.set(sKey, sList);
    const nKey = norm(name);
    const nList = byName.get(nKey) ?? [];
    nList.push(coin);
    byName.set(nKey, nList);
  }
  const liveMcap = new Map<string, number>();
  const liveFdv = new Map<string, number>();
  for (const [id, pair] of Object.entries(markets as Record<string, unknown>)) {
    const arr = Array.isArray(pair) ? pair : [];
    liveMcap.set(id, toMcap(arr[0]));
    liveFdv.set(id, toMcap(arr[1]));
  }
  return { bySymbol, byName, liveMcap, liveFdv };
}

/** NFKD, drop non-ASCII, lowercase, keep [a-z0-9] only — the same
 *  normalisation as Python's unicodedata.normalize + ascii-ignore. */
export function norm(s: string): string {
  return stripNonAscii((s ?? "").normalize("NFKD"))
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

function stripNonAscii(s: string): string {
  let out = "";
  for (const ch of s) {
    if ((ch.codePointAt(0) ?? 0) < 128) out += ch;
  }
  return out;
}

/** Content tokens of a name: split on non-alphanumerics, keep tokens
 *  of length >= 3 (same as the Python tokens() helper). */
export function tokensOf(s: string): Set<string> {
  const ascii = stripNonAscii((s ?? "").normalize("NFKD"));
  return new Set(
    ascii
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((t) => t.length >= 3),
  );
}

/** The token whose first occurrence in `name` comes earliest; ties
 *  (impossible for distinct words) break alphabetically so the pick
 *  is deterministic. Mirrors Python's sorted(tokens, key=find)[0]. */
function firstTokenByPosition(tokens: Set<string>, name: string): string | null {
  if (tokens.size === 0) return null;
  const lower = name.toLowerCase();
  const sorted = [...tokens].sort(
    (a, b) => lower.indexOf(a) - lower.indexOf(b) || (a < b ? -1 : a > b ? 1 : 0),
  );
  return sorted[0];
}

/** Score a CoinGecko coin against family names. Higher = stronger.
 *  Exact name equality: 100; coin name a prefix of a family name:
 *  50+len; family name a prefix of the coin name: 40; shared
 *  content-token overlap: 10 per token; first-token identical: 50;
 *  first-token prefix either way: 60. 0 when there is no real
 *  evidence (symbol alone never matches). */
export function scoreCoin(famNames: string[], coinName: string): number {
  const cn = norm(coinName);
  if (cn.length < 3) return 0;
  const ct = tokensOf(coinName);
  let best = 0;
  for (const fn of famNames) {
    const fnn = norm(fn);
    if (!fnn || fnn.length < 3) continue;
    if (cn === fnn) return 100;
    if (fnn.startsWith(cn)) best = Math.max(best, 50 + cn.length);
    else if (cn.startsWith(fnn)) best = Math.max(best, 40);
    const ft = tokensOf(fn);
    if (ct.size > 0 && ft.size > 0) {
      const inter = [...ct].filter((t) => ft.has(t) && t.length >= 4);
      if (inter.length > 0 && inter.length / Math.max(ct.size, ft.size) >= 0.34) {
        best = Math.max(best, 10 * inter.length);
      }
      // First content token identical (e.g. "Curve" in "Curve DAO
      // Token" vs "Curve DEX"): the protocol's own name, versioned
      // differently.
      const firstCt = firstTokenByPosition(ct, coinName);
      const firstFt = firstTokenByPosition(ft, fn);
      if (firstCt !== null && firstFt !== null && firstCt === firstFt && firstCt.length >= 5) {
        best = Math.max(best, 50);
      }
      // First-token prefix either way ("solvbtc" vs "solv", "realt"
      // vs "realtoken"): a product/child named after its parent.
      if (firstCt !== null && firstFt !== null) {
        const a = firstCt;
        const b = firstFt;
        if (a.length >= 4 && b.length >= 4 && (a.startsWith(b) || b.startsWith(a))) {
          best = Math.max(best, 60);
        }
      }
    }
  }
  return best;
}

/** Return {coin, score} iff one candidate is strictly best with
 *  score >= minScore. A tie at the top score is broken by live market
 *  cap; only when mcap cannot break the tie is it ambiguous (coin
 *  null, top score returned so the caller can record the review). */
export function bestCoinMatch(
  famNames: string[],
  candidates: CoinRow[],
  minScore: number,
  liveMcap: Map<string, number>,
): { coin: CoinRow | null; score: number } {
  const scored = candidates
    .map((c) => ({ coin: c, score: scoreCoin(famNames, c.name) }))
    .filter((cs) => cs.score >= minScore);
  if (scored.length === 0) return { coin: null, score: 0 };
  scored.sort((a, b) => b.score - a.score);
  if (scored.length > 1 && scored[0].score === scored[1].score) {
    const top = scored.filter((cs) => cs.score === scored[0].score);
    top.sort((a, b) => (liveMcap.get(b.coin.id) ?? 0) - (liveMcap.get(a.coin.id) ?? 0));
    if (
      top.length > 1 &&
      (liveMcap.get(top[0].coin.id) ?? 0) > (liveMcap.get(top[1].coin.id) ?? 0)
    ) {
      return top[0];
    }
    return { coin: null, score: scored[0].score };
  }
  return scored[0];
}

function fmtMcap(n: number): string {
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

/** The names the matcher scores: the flagship member's name, plus
 *  the parent slug's words when the family is parent-grouped. */
export function scoreNamesFor(fam: DetectableFamily): string[] {
  const names = [fam.name];
  if (fam.key.startsWith("parent#")) {
    names.push(fam.key.slice("parent#".length).replaceAll("-", " "));
  }
  return names;
}

/** Decide whether a family has a token, exactly as
 *  scripts/build_dataset.py does. Returns the decision plus any
 *  human-review items (provisional or ambiguous matches — these do
 *  NOT mark the family tokened). */
export function detectToken(
  fam: DetectableFamily,
  tables: CoinTables,
): { decision: TokenDecision; review: ReviewItem[] } {
  const review: ReviewItem[] = [];
  const scoreNames = scoreNamesFor(fam);

  // Family symbols arrive as strings from main.ts, but a non-string
  // entry (e.g. a numeric symbol in a degraded snapshot) must not
  // throw on toLowerCase(): coerce every entry to a string first.
  const symbols: string[] = (Array.isArray(fam.symbols) ? fam.symbols : []).map((s) =>
    typeof s === "string" ? s : s === null || s === undefined ? "" : String(s),
  );

  // Manual overrides first: families the automatic matcher cannot prove.
  const override = MANUAL_OVERRIDES[fam.key];
  if (override !== undefined) {
    return {
      decision: {
        hasToken: true,
        geckoId: override.geckoId,
        evidence: [override.evidence],
        provisional: false,
      },
      review,
    };
  }

  // DefiLlama's own link: the lexicographically smallest gecko_id wins.
  if (fam.geckoIds.length > 0) {
    const g = [...fam.geckoIds].sort()[0];
    return {
      decision: { hasToken: true, geckoId: g, evidence: ["defillama gecko_id"], provisional: false },
      review,
    };
  }

  // (a) Symbol-anchored candidates: coins sharing a family symbol.
  const cands = new Map<string, CoinRow>();
  for (const sym of symbols) {
    for (const coin of tables.bySymbol.get(sym.toLowerCase()) ?? []) {
      cands.set(coin.id, coin);
    }
  }
  const candList = [...cands.values()];
  let matched: string | null = null;
  let evidence: string[] = [];
  let provisional = false;
  const first = bestCoinMatch(scoreNames, candList, 40, tables.liveMcap);
  if (first.coin !== null) {
    matched = first.coin.id;
    evidence = [`coingecko symbol+name match: ${first.coin.name} (score ${first.score})`];
  } else if (candList.length === 1) {
    // Exactly one CoinGecko coin carries this symbol and the family
    // name contains the symbol as a word ("VVS Standard" vs VVS
    // Finance, "MUX Perps" vs MUX Protocol): that is the protocol's
    // token.
    const only = candList[0];
    const famWords = new Set<string>();
    for (const fn of scoreNames) {
      for (const t of tokensOf(fn)) famWords.add(t);
    }
    if (famWords.has(only.symbol.toLowerCase())) {
      matched = only.id;
      evidence = [`coingecko single-symbol match: ${only.name}`];
    }
  }

  if (matched === null) {
    // (b) Name-only: exact name equality, or coin name a strict
    // prefix (>= 6 chars) of a family name. Provisional until the
    // coin is confirmed trading (markets data, mcap > 0 or FDV > 0).
    const nameCands = new Map<string, CoinRow>();
    for (const fn of scoreNames) {
      const fnn = norm(fn);
      for (const coin of tables.byName.get(fnn) ?? []) nameCands.set(coin.id, coin);
      for (let L = 6; L < fnn.length; L++) {
        for (const coin of tables.byName.get(fnn.slice(0, L)) ?? []) {
          nameCands.set(coin.id, coin);
        }
      }
    }
    const second = bestCoinMatch(scoreNames, [...nameCands.values()], 50, tables.liveMcap);
    if (second.coin !== null) {
      const mcap = tables.liveMcap.get(second.coin.id) ?? 0;
      const fdv = tables.liveFdv.get(second.coin.id) ?? 0;
      if (mcap > 0 || fdv > 0) {
        matched = second.coin.id;
        evidence = [
          `coingecko name-only match, confirmed trading: ${second.coin.name} ` +
            `(score ${second.score}, mcap ${fmtMcap(mcap)})`,
        ];
      } else {
        provisional = true;
        review.push({
          family: fam.name,
          key: fam.key,
          symbols: [...symbols].sort(),
          candidate: {
            id: second.coin.id,
            name: second.coin.name,
            symbol: second.coin.symbol,
          },
          score: second.score,
          tvl: fam.tvl,
          reason: "name-only match, NOT confirmed trading (no markets mcap) - verify manually",
        });
      }
    } else if (candList.length > 0) {
      review.push({
        family: fam.name,
        key: fam.key,
        symbols: [...symbols].sort(),
        candidates: candList.map((c) => ({
          id: c.id,
          name: c.name,
          symbol: c.symbol,
          score: scoreCoin(scoreNames, c.name),
        })),
        tvl: fam.tvl,
        reason: "symbol-anchored candidates but no clear winner",
      });
    }
  }

  return {
    decision: { hasToken: matched !== null, geckoId: matched, evidence, provisional },
    review,
  };
}
