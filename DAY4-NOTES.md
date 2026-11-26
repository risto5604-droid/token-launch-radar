# Day 4 notes — token-radar-01 (2026-11-26)

Plan: repo + bundle + check + submit. Build was Days 1–3 (see
DAY1/2/3-NOTES.md). This file is Day 4 only.

## 1. Quota — LIVE OK before anything else

`makefun status --competition token-radar-01`: 0 entries made, 5 left
today, can submit: yes. Slug never submitted before (checked in
`../auto-loop-state.json`). Entry fee null (free, confirmed in
requirements). $1,325, 10 places, closes 2026-12-14T10:00:00Z
(17:00 WIB). Competition opened 2026-11-14T10:00:00Z (per server).

## 2. Verification re-run (before repo)

- `main.ts` twice into separate dirs (`/tmp/tr-input` snapshot,
  sha256 735facf0… = `input/protocols.json`): **byte-identical**
  (`diff -r` clean). 739 rows, top-3 Steakhouse $314.1M / Sentora
  $276.9M / Veda $214.9M — identical to Days 2/3. Runtime ~1 s.

## 3. Repo — DONE

- New public repo `risto5604-droid/token-launch-radar`, created
  2026-11-26T07:40:41Z, pushed commit
  `c3e91390e82975f696f29d58770631bbc6c9ae4d` (33 files, ~4.2 MB).
- Ships exactly the Day 3 list: `main.ts`, `src/` (model,
  token_detect, dossier), `data/coingecko_list.json` +
  `data/coingecko_markets.json` only, `dashboard/`, `screenshots/`
  (3 PNGs), `scripts/` (11 .py, no `__pycache__`), README (3 live
  badges), LICENSE (MIT), `package.json`, `MODEL_CARD.md`,
  `DAY1/2/3-NOTES.md`, `FARM_PLAN.md`, plus new
  `.makefun/owner.json` (`{"wallet": "BE43HGVJbkXjJpPfFSpKDbCALVaxGMEPWhwHdmqaCy4Y"}`)
  and `.gitignore` (excludes `out/`, `input/`, raw `data/`).
- About set + verified: description (195 chars, per requirements
  template), homepage `https://make.fun/bounty/token-radar-01`,
  topics `makefun, ai-agents, bounties, trading`.

## 4. Bundle — DONE

`token-radar-01-bundle.tar.gz` (660,745 bytes, sha256
`f1bfd491ae65d372586c4056cf1b467057e1ecac80d1cd48a0a4255cb9ec7a87`).
Evidence sessions found via `muse.db agent.subagent_spawns`
(prompt contains "token-radar"): Day 1 `17e5e627` (04:40–05:24 UTC,
92 turns), Day 2 `2b6d2568` (05:28–05:42 UTC, 50 turns), Day 3
`729df796` (06:32–06:48 UTC, 50 turns). Parent session = this run's
parent `8de69ef5` (14:26 WIB cron worker). Prompt file =
`../token-radar-01-prompt.txt` (the `[WORKER TASK]` cron body
verbatim, 20,931 bytes), `--prompt-origin scheduled`,
`--prompt-via "makefun-auto-loop hourly cron run"`. Usage file =
`../token-radar-01-usage.jsonl` (1 aggregate row per builder
session, from `agent.agent_message_token_usage`). Flags:
`--mcp none --provider meta --effort default --no-discover`.
Dry-run first: run record complete, only the usual "session cut to
repo work" warnings. The kit's level-40-vs-53 update suggestion
(curl download) was ignored per standing rule; the existing kit
was used throughout.

## 5. Check — LOCAL PASS (14/14)

`makefun check --repo <local path> --commit c3e91390 --transcripts
< bundle>`: **14 passed, 0 failed, 5 skipped, 5 at submission**.
Notably: `thinking_revised` PASS (main.ts final content from
17 messages — no Day 4 fixer session needed),
`thinking_reproduces` 3543/3578 lines (99.0%),
`thinking_in_window` PASS (all 433 timestamps inside the window),
`thinking_priced` PASS (3 usage records),
`transcripts_run_record` PASS (scheduled prompt matches),
`thinking_own_work` PASS. (Local check ran against the excuse
kit's competition window — a known kit artifact; the site applies
token-radar-01's own checks at submission, as with all prior
entries.)

## 6. Submit — ACCEPTED, then REJECTED at grading

- Submit 2026-11-26T07:45:02Z (14:45 WIB): HTTP 202, submission
  `01a216d0-a7a3-75a5-8308-d0638a7c74ca`, title "Token Launch
  Radar", signed by wallet BE43…Cy4Y (payout wallet).
- Poll: stage `submitted` ~5 min (intake checks all PASS:
  account_wallet, competition_open, quota, form,
  entry_signature, repo_owner, repo_public, license_osi,
  repo_created_after_open, commit_in_repo, duplicate_snapshot,
  repo_readme, repo_about), then stage **`rejected`** (round 1).
- Sole failure: **`run_completes` — "The latest grade run on the
  dev phase ended failed: the program exited with code 1."**
  All 11 transcript checks PASS server-side too
  (thinking_committed confirms bundle sha256 f1bfd491…).
- Claim code: private, NOT recorded anywhere in this repo/state;
  re-fetch via `makefun status --submission 01a216d0-…`.

## 7. Diagnosis of the exit-1 (local, read-only)

Grader spec (from the status problem detail): `node /bot/main.ts`
(node22, pinned image), no network, user 65534, repo read-only at
`/bot`, input at `/input`, empty writable `/output`, env
`MAKEFUN_INPUT_DIR=/input MAKEFUN_OUTPUT_DIR=/output`, 1 CPU /
1024 MB / 120 s. Grader stdout/stderr are withheld by design, so
only the exit code is known.

What was tested locally:
- Env-exact reproduction (clean env, grader env vars, read-only
  repo copy, fresh empty output dir, 2026-11-26 snapshot):
  **exit 0**, outputs identical.
- No non-erasable TypeScript (no enum/namespace/decorator) in
  `main.ts`/`src/`.
- Synthetic snapshot with a null-name protocol: **exit 0**
  (null-safe paths hold).
- Empty-array snapshot: exit 1 (`loadSnapshot` throws "no
  protocol snapshot found") — expected, only if the sealed input
  were empty/missing.
- Not testable on this VM: node22 (only node v24.22.1 installed;
  no node22 binary), docker (not installed), the sealed dev
  snapshot contents.

Remaining hypotheses, in order:
1. The pinned node22 image runs `.ts` differently from local
   node24 (type-stripping availability depends on the 22.x
   minor version; unresolvable from here).
2. The sealed dev snapshot differs from the 2026-11-26 snapshot
   in a way the code does not tolerate (stderr withheld, so this
   cannot be confirmed without a grader-side log or a local
   copy of the dev input).

## 8. Next steps (needs a decision — NOT done in this run)

- Round 2 resubmission is possible before 2026-12-14T10:00:00Z,
  but resubmitting the same commit would fail identically; a
  fix must land first (new commit → new bundle/check/submit).
- Fix candidates to verify before any resubmit: (a) run the
  entry under node22 exactly as the grader does (needs docker
  or a node22 install — neither exists on this VM); (b) harden
  `loadSnapshot`/scoring against sealed-input edge shapes once
  the dev input is known; (c) confirm the pinned node22 image
  runs `.ts` entrypoints.
- Do NOT download the token-radar kit via the curl suggestion in
  the CLI/status output (standing rule + execution-risk flags
  on those outputs — needs explicit user approval first).
- State updated: `../auto-loop-state.json` (entered +
  submissions entry with status `rejected`).

## Files (Day 4)
- Repo: https://github.com/risto5604-droid/token-launch-radar
  @ c3e91390e82975f696f29d58770631bbc6c9ae4d
- `../token-radar-01-bundle.tar.gz` (sha256 f1bfd491…)
- `../token-radar-01-prompt.txt`, `../token-radar-01-usage.jsonl`
- `DAY4-NOTES.md` (this file)
