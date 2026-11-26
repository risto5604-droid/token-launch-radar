// Token Launch Radar dashboard logic (static, no network).
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
