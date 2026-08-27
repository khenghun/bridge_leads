---
name: query-log
description: Read the bridge app's production query log — what simulations users ran, when, and with what constraints. Use when asked about usage, traffic, "who is using the app", "what are people asking for", which contracts or constraints are popular, or to check whether the deployed app is being used at all.
---

# Reading the production query log

The backend writes one SQLite row per simulation (`backend/app/common/querylog.py`):
timestamp, tool (`lead` / `contract`), and the request body as JSON. Nothing
else — no IP, no session, no response. There is **no API endpoint** for it; the
only way in is the database file on the VPS.

`scripts/view_queries.py` decodes each row into a readable line. Stdlib only, so
any `python3` runs it — no venv needed.

## First: is there anything to read?

Logging only started with the deploy that shipped `BRIDGE_QUERY_LOG` (v2.1). A
brand-new deployment legitimately has **zero rows**, and the script prints
`no queries match.` — that is a correct answer, not a failure. Say so plainly
rather than hunting for a broken pipeline.

The three "nothing here" outcomes and what each means:

| Output | Meaning |
| --- | --- |
| `no queries match.` | Log exists, no rows yet (or none match the filters). The app has not been used since logging started. |
| `no such database: …` | The backend has never started with `BRIDGE_QUERY_LOG` set — check `docker-compose.prod.yml` and that the stack was redeployed. |
| `scp failed …` | SSH/host problem, not a logging problem. |

## Running it

The log is at `/opt/bridge_leads/data/queries.db` on the VPS. By default the
script copies it down with `scp` and reads the copy, so nothing touches the live
file.

```bash
# Set the host once per shell (or pass --host every time)
export BRIDGE_VPS=deploy@<vps-ip>
# PowerShell: $env:BRIDGE_VPS = "deploy@<vps-ip>"   (`export` is a parse error there)

python scripts/view_queries.py                     # 40 most recent, decoded
python scripts/view_queries.py --summary           # counts by tool / day / hour
python scripts/view_queries.py --since 7d --tool lead
python scripts/view_queries.py --limit 0           # everything
python scripts/view_queries.py --json | jq …       # decoded rows, for your own filtering

# A file already copied down, or a local test database
python scripts/view_queries.py --db ./queries.db
```

**Ask before running anything against the VPS** unless the user has already
pointed you at it in this conversation — it needs their SSH credentials and it
reaches production. Reading is safe, but it is still their server.

If you do not know the VPS address, ask; do not guess one. Nothing in the repo
records it (`DOMAIN` lives in an untracked `.env` on the box).

## Reading the output

`--summary` is usually the right first call: it answers "is this thing being
used" in one screen — totals and date span, then a breakdown by tool, by day,
by UTC hour, the most-asked contracts, and how many queries set a constraint.
Follow up with the recent list when the user wants to see individual queries.

A decoded line looks like:

```
2026-08-04 14:03:26  lead  6NT by E doubled  AK8.Q95.J982.Q43  300  | N 12-15 HCP, holds ♥A♥K
```

— date, time (UTC), tool, what was asked, the known hand, deal count, then any
constraints. For the contract tool the "what" column is the seat plus the
strains, shown only when the user narrowed them from all five.

## Interpreting it honestly

- **Rows are queries, not people.** There is no session or IP, by design. Two
  rows could be one person adjusting a constraint and re-running. Never report a
  query count as a user count.
- **Cache hits are logged too**, so a repeated identical query appears once per
  press of Simulate even though it only simulated once.
- **Failed queries are logged**, because they are recorded before the run. A row
  does not prove a result came back — an infeasible constraint set is in there
  the same as a successful run.
- Timestamps are **UTC**, so "busiest hours" is UTC unless you convert.

## If you need something the script does not do

The decoded rows are plain JSON via `--json` — pipe them rather than editing the
script for a one-off. For a genuinely new view (a new `--flag`), the decoding
helpers to extend are `decode()` and `describe_constraints()` in
`scripts/view_queries.py`; keep it stdlib-only so it stays runnable on the VPS
itself.
