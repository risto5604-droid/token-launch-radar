#!/usr/bin/env python3
"""Generate the token-radar dashboard (Day 3, step 2).

Reads out/board.json + data/farm_plans.json + data/comps.json +
data/coingecko_markets.json and writes dashboard/:
  index.html  -- the page (data embedded at build time, so it opens
                 from disk with no network request at all)
  app.js      -- table rendering, sorting, filtering, detail view
  data.json   -- the same payload as a machine-readable artifact

Deterministic: sorted keys, fixed ordering, no timestamps (the only
date string is the fixed snapshot date "2026-11-26").

Detail view comps: the 3 nearest launched comps by category + TVL --
same-category first (nearest by |log TVL ratio|), filled from all
launched comps with a quoted FDV when the category has fewer than 3.
FDV comes from the CoinGecko markets table (markets[id] = [mcap, fdv]).
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
OUT = HERE / "dashboard"
SNAPSHOT_DATE = "2026-11-26"

MODEL_SUMMARY = {
    "cv_median_ratio": 3.43,
    "walk_forward_median_ratio": 3.20,
    "conformal_80_log": 2.32,
    "conformal_80_factor": 10.2,
    "launch_odds_auc": 0.70,
    "launch_odds_brier": 0.221,
}


def money(n: float) -> str:
    if n >= 1e9:
        return f"${n / 1e9:.2f}B"
    if n >= 1e6:
        return f"${n / 1e6:.1f}M"
    if n >= 1e3:
        return f"${n / 1e3:.0f}k"
    return f"${n:.0f}"


def nearest_comps(row, comps_by_cat, all_comps):
    """3 nearest launched comps: same category first, then any category.

    Distance is |log(TVL_row / TVL_comp)|; ties break by comp key.
    Each comp carries its CoinGecko FDV (markets table) and whether it
    shares the row's category.
    """
    def dist(c):
        return abs(math.log(row["tvl"] / c["tvl"])) if c["tvl"] > 0 else 1e9

    picked: list[dict] = []
    seen: set[str] = set()
    for pool in (comps_by_cat.get(row["category"], []), all_comps):
        for c in sorted(pool, key=lambda c: (dist(c), c["key"])):
            if c["key"] in seen:
                continue
            seen.add(c["key"])
            picked.append({
                "key": c["key"],
                "name": c["name"],
                "category": c["category"],
                "tvl_usd": c["tvl"],
                "fdv_usd": c["fdv_usd"],
                "same_category": c["category"] == row["category"],
            })
            if len(picked) == 3:
                return picked
    return picked


def main() -> None:
    board = json.load(open(HERE / "out" / "board.json"))
    plans = json.load(open(DATA / "farm_plans.json"))
    comps_raw = json.load(open(DATA / "comps.json"))
    markets = json.load(open(DATA / "coingecko_markets.json"))

    # Launched comps with a quoted FDV (markets[id] = [mcap, fdv]).
    comps = []
    for c in comps_raw:
        gid = c.get("gecko_id")
        if not gid or gid not in markets:
            continue
        fdv = markets[gid][1]
        if not fdv:
            continue
        comps.append({
            "key": c["key"], "name": c["name"], "category": c["category"],
            "tvl": c["tvl"], "fdv_usd": fdv,
        })
    comps.sort(key=lambda c: c["key"])
    comps_by_cat: dict[str, list[dict]] = {}
    for c in comps:
        comps_by_cat.setdefault(c["category"], []).append(c)

    rows = []
    for r in board["rows"]:
        plan = plans[r["key"]]
        rows.append({
            "rank": r["rank"],
            "key": r["key"],
            "name": r["name"],
            "slug": r["slug"],
            "tvl": r["tvl"],
            "chains": r["chains"],
            "category": r["category"],
            "listed_at": r["listedAt"],
            "implied_fdv_usd": r["impliedFdvUsd"],
            "implied_fdv_lo80_usd": r["impliedFdvLo80Usd"],
            "implied_fdv_hi80_usd": r["impliedFdvHi80Usd"],
            "launch_probability": r["launchProbability"],
            "expected_value_usd": r["expectedValueUsd"],
            "plan": {
                "template": plan["template"],
                "tvl_tier": plan["tvl_tier"],
                "age_days": plan["age_days"],
                "chains": plan["chains"],
                "url": plan["url"],
                "twitter": plan["twitter"],
                "steps": plan["steps"],
            },
            "comps": nearest_comps(r, comps_by_cat, comps),
        })

    payload = {
        "meta": {
            "snapshot_date": SNAPSHOT_DATE,
            "rows": len(rows),
            "snapshot_protocols": board["snapshotProtocols"],
            "families": board["families"],
            "tokened_families_excluded": board["tokenedFamilies"],
            "model": MODEL_SUMMARY,
        },
        "rows": rows,
    }
    data_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    (OUT).mkdir(parents=True, exist_ok=True)
    (OUT / "data.json").write_text(data_json + "\n", encoding="utf-8")
    (OUT / "app.js").write_text(APP_JS, encoding="utf-8")
    (OUT / "index.html").write_text(
        INDEX_HTML.replace("__DATA_JSON__", data_json), encoding="utf-8"
    )
    total = sum(p.stat().st_size for p in OUT.iterdir())
    print(f"dashboard/: {len(rows)} rows, {len(comps)} launched comps with FDV, "
          f"{total} bytes total")
    print("top-3 comps check:",
          [(r["name"], [(c["name"], money(c["fdv_usd"])) for c in r["comps"]])
           for r in rows[:1]])


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Token Launch Radar — 739 pre-token protocols</title>
<style>
  :root { color-scheme: light; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0 auto;
    max-width: 1100px; padding: 24px 16px 64px; color: #1a1a1a; background: #fff; }
  h1 { font-size: 28px; margin: 0 0 4px; }
  .sub { color: #555; margin: 0 0 16px; }
  .honest { background: #f6f6f2; border: 1px solid #ddd; border-radius: 8px;
    padding: 12px 16px; margin: 0 0 20px; font-size: 14px; line-height: 1.5; }
  .honest b { color: #000; }
  .filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 0 0 12px; }
  .filters label { font-size: 13px; color: #444; display: flex; flex-direction: column; gap: 2px; }
  .filters input, .filters select { padding: 6px 8px; font-size: 14px; border: 1px solid #bbb; border-radius: 4px; }
  .count { font-size: 13px; color: #555; margin: 0 0 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { padding: 7px 8px; border-bottom: 1px solid #e3e3e3; text-align: right; white-space: nowrap; }
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), th:nth-child(3), td:nth-child(3) { text-align: left; }
  th { cursor: pointer; user-select: none; background: #fafafa; position: sticky; top: 0; }
  th:hover { background: #f0f0f0; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: #f7f7ff; }
  .num { font-variant-numeric: tabular-nums; }
  .interval { color: #666; font-size: 12px; display: block; }
  #detail { border: 1px solid #bbb; border-radius: 8px; padding: 16px 20px; margin: 0 0 20px; background: #fbfbff; display: none; }
  #detail h2 { margin: 0 0 4px; font-size: 20px; }
  #detail .stats { display: flex; flex-wrap: wrap; gap: 24px; margin: 12px 0; }
  #detail .stat b { display: block; font-size: 18px; }
  #detail .stat span { font-size: 12px; color: #555; }
  #detail ol { margin: 8px 0; padding-left: 20px; line-height: 1.55; }
  #detail .ev { font-size: 12px; color: #666; }
  #detail table { font-size: 13px; margin-top: 8px; }
  #detail th { cursor: default; position: static; }
  #detail tbody tr { cursor: default; }
  #detail tbody tr:hover { background: none; }
  .close { float: right; cursor: pointer; border: 1px solid #bbb; background: #fff; border-radius: 4px; padding: 2px 8px; }
  a { color: #1a4fd6; }
</style>
</head>
<body>
<h1>Token Launch Radar</h1>
<p class="sub">739 pre-token protocols, ranked by expected value = implied FDV &times; launch probability. Snapshot 2026-11-26 (DefiLlama + CoinGecko).</p>
<div class="honest"><b>How to read this board.</b> The pricing model is an OLS fit on log FDV of 445 launched protocols. Out-of-sample it is wrong by a median factor of <b>3.20&times;</b> (walk-forward) and the 80% prediction interval spans <b>&times;10.2</b> — so every implied FDV below is shown <b>with its interval, never alone</b>. Launch odds are a logistic model (AUC 0.70). The ranking is better than the levels (walk-forward Spearman 0.59); treat the top of the board as a watchlist to farm, not a price forecast. Full model card: MODEL_CARD.md in the repo.</div>
<div id="detail"></div>
<div class="filters">
  <label>Category <select id="f-category"><option value="">All categories</option></select></label>
  <label>Min TVL (USD) <input id="f-min-tvl" type="number" min="0" step="100000" placeholder="50000"></label>
  <label>Min launch odds <input id="f-min-odds" type="number" min="0" max="1" step="0.05" placeholder="0"></label>
  <label>Search <input id="f-search" type="text" placeholder="name or category"></label>
  <button id="f-reset" type="button">Reset</button>
</div>
<p class="count" id="count"></p>
<table id="board">
  <thead><tr>
    <th data-k="rank">Rank</th><th data-k="name">Protocol</th><th data-k="category">Category</th>
    <th data-k="tvl">TVL</th><th data-k="implied_fdv_usd">Implied FDV</th>
    <th data-k="launch_probability">Launch odds</th><th data-k="expected_value_usd">Expected value</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
<script id="board-data" type="application/json">__DATA_JSON__</script>
<script src="app.js"></script>
</body>
</html>
"""

APP_JS = """// Token Launch Radar dashboard logic (static, no network).
// Data is embedded in index.html at build time; this file only renders.
(function () {
  var DATA = JSON.parse(document.getElementById("board-data").textContent);
  var rows = DATA.rows;
  var byKey = {};
  rows.forEach(function (r) { byKey[r.key] = r; });

  function money(n) {
    if (n >= 1e9) return "$" + (n / 1e9).toFixed(2) + "B";
    if (n >= 1e6) return "$" + (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return "$" + (n / 1e3).toFixed(0) + "k";
    return "$" + n.toFixed(0);
  }
  function pct(p) { return (p * 100).toFixed(1) + "%"; }
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  var state = { sortKey: "rank", sortDir: 1, category: "", minTvl: 0, minOdds: 0, search: "" };

  var catSel = document.getElementById("f-category");
  var cats = [];
  rows.forEach(function (r) { if (cats.indexOf(r.category) < 0) cats.push(r.category); });
  cats.sort();
  cats.forEach(function (c) {
    var o = document.createElement("option");
    o.value = c; o.textContent = c; catSel.appendChild(o);
  });

  function filtered() {
    var q = state.search.toLowerCase();
    return rows.filter(function (r) {
      if (state.category && r.category !== state.category) return false;
      if (r.tvl < state.minTvl) return false;
      if (r.launch_probability < state.minOdds) return false;
      if (q && r.name.toLowerCase().indexOf(q) < 0 && r.category.toLowerCase().indexOf(q) < 0) return false;
      return true;
    }).sort(function (a, b) {
      var k = state.sortKey, d = state.sortDir;
      var av = a[k], bv = b[k];
      if (typeof av === "string") return d * (av < bv ? -1 : av > bv ? 1 : 0);
      return d * (av - bv);
    });
  }

  function render() {
    var list = filtered();
    document.getElementById("count").textContent =
      list.length + " of " + rows.length + " protocols shown";
    var tb = document.getElementById("rows");
    tb.innerHTML = list.map(function (r) {
      return '<tr data-key="' + esc(r.key) + '"><td class="num">' + r.rank + '</td>' +
        '<td>' + esc(r.name) + '</td><td>' + esc(r.category) + '</td>' +
        '<td class="num">' + money(r.tvl) + '</td>' +
        '<td class="num">' + money(r.implied_fdv_usd) +
        '<span class="interval">80%: ' + money(r.implied_fdv_lo80_usd) + ' &ndash; ' + money(r.implied_fdv_hi80_usd) + '</span></td>' +
        '<td class="num">' + pct(r.launch_probability) + '</td>' +
        '<td class="num"><b>' + money(r.expected_value_usd) + '</b></td></tr>';
    }).join("");
  }

  function showDetail(key) {
    var r = byKey[key];
    var el = document.getElementById("detail");
    if (!r) { el.style.display = "none"; el.innerHTML = ""; return; }
    var p = r.plan;
    var links = "";
    if (p.url) links += '<a href="' + esc(p.url) + '">official site</a>';
    if (p.twitter) links += (links ? " &middot; " : "") + '<a href="https://x.com/' + esc(p.twitter) + '">@' + esc(p.twitter) + "</a>";
    var steps = p.steps.map(function (s) {
      return "<li>" + esc(s.text) + ' <span class="ev">[' + s.evidence.join(", ") + "]</span></li>";
    }).join("");
    var comps = r.comps.map(function (c) {
      return "<tr><td>" + esc(c.name) + "</td><td>" + esc(c.category) +
        (c.same_category ? "" : " (other)") + '</td><td class="num">' + money(c.tvl_usd) +
        '</td><td class="num">' + money(c.fdv_usd) + "</td></tr>";
    }).join("");
    var age = p.age_days === null ? "unknown" : p.age_days + " days";
    el.innerHTML = '<button class="close" id="d-close">Close</button>' +
      "<h2>#" + r.rank + " " + esc(r.name) + "</h2>" +
      "<div>" + esc(r.category) + " &middot; TVL " + money(r.tvl) + " (" + esc(p.tvl_tier) + ") &middot; " +
      r.chains + " chains (" + esc(p.chains.join(", ")) + ") &middot; listed " + age + " ago" +
      (links ? " &middot; " + links : "") + "</div>" +
      '<div class="stats">' +
      '<div class="stat"><b>' + money(r.implied_fdv_usd) + "</b><span>implied FDV</span></div>" +
      '<div class="stat"><b>' + money(r.implied_fdv_lo80_usd) + " &ndash; " + money(r.implied_fdv_hi80_usd) + "</b><span>80% interval (&times;10.2)</span></div>" +
      '<div class="stat"><b>' + pct(r.launch_probability) + "</b><span>launch probability</span></div>" +
      '<div class="stat"><b>' + money(r.expected_value_usd) + "</b><span>expected value</span></div>" +
      "</div>" +
      "<h3>Farm plan (" + esc(p.template) + ")</h3><ol>" + steps + "</ol>" +
      '<p class="ev">Each step lists the snapshot fields it is grounded in. A points program is only ever mentioned as something to check in the docs — the snapshot records none.</p>' +
      "<h3>Nearest launched comps (same category first, by TVL)</h3>" +
      '<table><thead><tr><th>Protocol</th><th>Category</th><th>TVL</th><th>FDV</th></tr></thead><tbody>' + comps + "</tbody></table>";
    el.style.display = "block";
    document.getElementById("d-close").addEventListener("click", function () {
      history.replaceState(null, "", location.pathname + location.search);
      showDetail(null);
    });
    el.scrollIntoView({ block: "start" });
  }

  document.getElementById("rows").addEventListener("click", function (e) {
    var tr = e.target.closest("tr[data-key]");
    if (!tr) return;
    var params = new URLSearchParams(location.search);
    params.set("detail", tr.getAttribute("data-key"));
    history.replaceState(null, "", location.pathname + "?" + params.toString());
    showDetail(tr.getAttribute("data-key"));
  });
  document.querySelectorAll("#board th[data-k]").forEach(function (th) {
    th.addEventListener("click", function () {
      var k = th.getAttribute("data-k");
      if (state.sortKey === k) state.sortDir = -state.sortDir;
      else { state.sortKey = k; state.sortDir = k === "name" || k === "category" ? 1 : -1; }
      render();
    });
  });
  function bind(id, fn) { document.getElementById(id).addEventListener("input", fn); }
  bind("f-category", function (e) { state.category = e.target.value; render(); });
  bind("f-min-tvl", function (e) { state.minTvl = parseFloat(e.target.value) || 0; render(); });
  bind("f-min-odds", function (e) { state.minOdds = parseFloat(e.target.value) || 0; render(); });
  bind("f-search", function (e) { state.search = e.target.value; render(); });
  document.getElementById("f-reset").addEventListener("click", function () {
    state.category = ""; state.minTvl = 0; state.minOdds = 0; state.search = "";
    catSel.value = ""; document.getElementById("f-min-tvl").value = "";
    document.getElementById("f-min-odds").value = ""; document.getElementById("f-search").value = "";
    render();
  });

  // Deep links for screenshots / sharing: ?detail=<key>, ?category=, ?minTvl=, ?minOdds=, ?search=
  var params = new URLSearchParams(location.search);
  if (params.get("category")) { state.category = params.get("category"); catSel.value = state.category; }
  if (params.get("minTvl")) { state.minTvl = parseFloat(params.get("minTvl")) || 0; document.getElementById("f-min-tvl").value = state.minTvl; }
  if (params.get("minOdds")) { state.minOdds = parseFloat(params.get("minOdds")) || 0; document.getElementById("f-min-odds").value = state.minOdds; }
  if (params.get("search")) { state.search = params.get("search"); document.getElementById("f-search").value = state.search; }
  render();
  if (params.get("detail")) showDetail(params.get("detail"));
})();
"""


if __name__ == "__main__":
    main()
