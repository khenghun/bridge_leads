---
name: test-deployed
description: Regression-test the deployed bridge apps (lead/contract at bridge-leads, play solver at bridge-play) — or a local build — against a per-release checklist that grows with each product's changelog. Use after a deploy ("test prod", "check the deployed app", "smoke test", "did the release land"), before a release to pre-verify locally, or when asked whether a change regressed something.
---

# Regression-testing the deployed apps

Two products, two sites, one method: **every release in a product's changelog
has a section of checks, and the deployed site must pass the checks of every
release it claims to contain.** The checklist is append-only — a new release
adds a section, it never rewrites old ones — so running the whole file is the
regression suite and running the newest section is the release acceptance.

| Product | Prod | Local (see `run-apps` skill) | Changelog (version source of truth) | Checks |
| --- | --- | --- | --- | --- |
| Lead / contract | https://bridge-leads.icycookie.xyz | http://localhost:5173/ | `frontend/src/apps/changelog/releases.ts` | [`checks/lead.md`](checks/lead.md) |
| Play solver | https://bridge-play.icycookie.xyz | http://localhost:5174/play.html | `frontend/src/apps/play/changelog/releases.ts` | [`checks/play.md`](checks/play.md) |

Results are simulated with `seed=0`, so **identical inputs give identical
numbers on every box** — that is what lets the checks pin exact values
(a lead's IMPs to three decimals, a grade count) instead of "a table appears".
A pinned number that moves is either a regression or a deliberate engine
change; either way it is a finding to report, never something to silently
re-pin.

## Procedure

1. **Coverage gate — before touching a browser.**
   ```
   python scripts/regression.py coverage
   ```
   It reads both `releases.ts` files and both checklists and prints, per
   product: the version the deployed header should show (newest entry without
   `unreleased`), any entries still flagged `unreleased`, and **any release
   with no `## vX.Y` section in its checklist**. An uncovered release is a
   stop: write its checks first (one per user-visible bullet of the changelog
   entry — that is the mapping that keeps the suite honest), then continue.
   Exit code 1 = uncovered releases.

2. **Pick the tier.** Each check is tagged `[smoke]` or `[full]`.
   - After a deploy: run **smoke for the deployed product** (≈2–3 min of
     wall-clock, mostly DDS) **plus the full section of every release that
     deploy shipped** (the ones that just lost their `unreleased` flag).
   - Before a release, locally: the full section of the release under test.
   - Any engine change (`backend/engine/**`, `lib/bridge.ts`): **full, both
     products** — the pinned numbers are exactly what an engine change moves.

3. **Set the target.** Default is prod. For a local build boot it with the
   `run-apps` skill first, then substitute the local base URLs; the checks
   are written so nothing else changes. Health first, with curl, before any
   browser work:
   ```
   curl -s https://bridge-leads.icycookie.xyz/api/health        # {"status":"ok"}
   curl -s https://bridge-play.icycookie.xyz/api/play/health    # {"status":"ok"}
   ```
   Share-link checks need their URLs: `python scripts/regression.py urls`
   (`--base http://localhost:5173` for local) prints one per vector in
   `vectors/*.json` — those JSON files *are* the frozen requests; edit the
   JSON, never the URL.

4. **Run the checks with the Playwright MCP** (`mcp__playwright__*`), in
   checklist order, reading the expected values from the check itself. Per
   check record pass / fail / skipped-with-reason. Three habits that matter:
   - **Read the request body, not just the status** when a check says what
     the UI must *send* (`browser_network_request` on the POST) — a
     constraint the UI dropped still returns 200.
   - **Console** (`browser_console_messages`, level `warning`): 0 errors and
     0 warnings on prod; locally only the `favicon.ico` 404 is acceptable.
   - **Screenshots land in the repo root** — delete them before finishing.

5. **Log the run.**
   ```
   python scripts/regression.py log --product play --target prod --tier smoke+v1.2 --result pass --notes "…"
   ```
   appends one row to `docs/testing/REGRESSION-LOG.md` (date, product,
   version from `releases.ts`, target, the SHA `origin/main` points at — the
   deploy tags images with `github.sha` — tier, result, notes). Commit the
   row with whatever else the session commits; it is the audit trail that
   says "v1.2 passed on prod on this SHA".

6. **Report** as a table: check ID, result, the observed value where it
   differs from the pinned one. A failed pinned number gets the observed
   value beside the expected one so the reader can judge drift vs breakage.

## Adding checks for a new release (the part that keeps this regression-friendly)

When a release entry is added to `releases.ts`, add a `## vX.Y — <title>`
section to that product's checklist **in the same commit**. Rules:

- One check per changelog bullet, minimum. The check's first line names the
  bullet it guards, so a reader can trace check → promise.
- Tag the one or two most representative checks `[smoke]`; the rest `[full]`.
- **Pin numbers.** Run the check once on a known-good build and write the
  exact values into the check with the version and date they were pinned
  (`pinned v1.2 · 2026-09-01`). Invariants ("counts sum to 300") are the
  fallback when a value is legitimately unpinnable, not the default.
- Prefer a **share-link vector** (`vectors/<name>.json`, lead product) or a
  **built-in example hand** (play product) over hand-typed setups: they are
  reproducible by construction and the request is frozen in the repo.
- Never delete or edit an old section's expectations to make a run pass. If
  the engine changed on purpose, re-pin in a commit whose message says so,
  with the old value in the check's history note.

## Gotchas

- **A share link only auto-runs on a fresh document load.** The payload is
  read once at startup, so `browser_navigate` from one `#tool?s=…` hash to
  another on the same origin does *not* re-run — navigate to `about:blank`
  first, or `location.reload()` after setting the hash.
- **Playwright's `browser_wait_for` has its own timeout**; for a whole-table
  analysis or a 1000-deal run, wait on a string that only exists when the
  result is complete (`Biggest swings`, `Copy link`) with a generous `time`.
- **Hidden tabs keep their DOM.** On the lead site the other tools' results
  stay mounted; `browser_find` will report a "Copy link" that is hidden.
  Assert on visible elements (a `wait_for` on text resolves only visible
  ones).
- The play site's whole-table run is three sequential `/api/play/analyze`
  POSTs; a partial result with fewer is a failure even if the page looks
  filled.
- Prod runs on a 2-vCPU box with DDS capped at 2 threads per product: a
  300-deal lead run is ~5 s, a 150-deal contract run ~10 s, a 20-deal
  whole-table play analysis ~30 s. Ten times slower means the other
  product's container is saturating the box or a deploy is mid-flight —
  check with the `vps` skill before calling it a regression.
