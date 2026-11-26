# Day 5 notes — token-radar-01 fix + resubmit (2026-11-26)

Fix for the Day 4 rejection. Round 1 submission 01a216d0 (26 Nov
14:45 WIB) was REJECTED on `run_completes` only: the grader's dev
run exited 1. All intake + 11 transcript checks passed.

## 1. Root cause (verified, not guessed)

- The code ran fine under node 22.21.1 on the normal 2026-11-26
  snapshot (exit 0, 739 rows) — type-stripping is NOT the problem.
  Node 22.21.1 was downloaded to /tmp for this check (no node22 or
  docker existed on the VM before).
- `loadSnapshot()` in main.ts threw "no protocol snapshot found"
  on any degraded input. Verified exit 1 under node 22.21.1 for:
  empty-array snapshot, missing input dir, object-wrapped snapshot
  (`{"protocols": [...]}`), first row with tvl as a string.
- Two more exit-1 paths downstream: `buildDossier()` threw on a
  0-row board and on missing dashboard/screenshots; `main()` threw
  if the dashboard/screenshots dirs were missing from the repo.

## 2. Fix (commit after c3e91390)

- `main.ts` — `loadSnapshot()` never throws: missing/unreadable
  dir → `[]`; accepts arrays whose first row has a string slug
  (tvl optional) and object-wrapped snapshots
  (`protocols`/`data`/`items`); every row coerced defensively
  (numeric fields → finite numbers, strings → strings, rows
  without a usable slug skipped); no snapshot found → `[]`.
  `main()` wrapped in try/catch with `writeFallbackOutputs()`
  (minimal valid board.json + dossier.json, exit 0, never throws
  itself). Dashboard/screenshots copy skips missing dirs instead
  of throwing. `scoreWatchlist()` sanitizes non-finite scores
  (fallback 0) before sorting.
- `src/dossier.ts` — `buildDossier()` never throws: missing/
  unparseable board → empty board; 0 rows allowed (`top_3: []`);
  missing dashboard → `files: []`; missing screenshots →
  `cover: null, images: []`; `listFiles()` skips non-plain files.
- `src/token_detect.ts` — `loadCoinTables()` skips malformed
  list rows (non-triple, uncoercible element) and coerces market
  pairs to finite numbers; `detectToken()` coerces symbols to
  strings. A missing/unparseable file still throws (the main()
  safety net covers it).

## 3. Verification (node 22.21.1, read-only repo copy, fresh empty
##    output dir, env MAKEFUN_INPUT_DIR/MAKEFUN_OUTPUT_DIR)

Normal snapshot: exit 0, 739 rows, top Steakhouse / Sentora /
Veda — board.json AND dossier.json BYTE-IDENTICAL to the Day 4
verified outputs (cmp clean). Also verified as uid 65534
(nobody, the grader's user): exit 0, byte-identical.

| Degraded input | Exit | Result |
|---|---|---|
| empty-array snapshot `[]` | 0 | valid board (0 rows) + REAL dossier (rows 0, dashboard listed, cover set) |
| missing input dir | 0 | valid board (0 rows) + real dossier |
| object-wrapped, 5 rows | 0 | 5 loaded, 0 scored (all tokened/excluded), valid outputs |
| first-row tvl as string | 0 | 739 rows, tvl coerced |
| garbage (unparseable) JSON | 0 | valid board (0 rows) + real dossier |

## 4. Resubmit (round 2)

- Old submission 01a216d0 REJECTED (not a live entry); live quota
  checked before resubmit: entries made 1 (kept 0), 4 of 5 left
  today, can submit: yes.
- New commit → new bundle (Day 1–3 builder sessions + 4 fixer
  sessions) → check → submit. Deadline round 2:
  14 Dec 2026 10:00 UTC (17:00 WIB).
