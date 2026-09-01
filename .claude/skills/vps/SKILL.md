---
name: vps
description: SSH into the bridge production VPS (Vultr box that runs the lead and play stacks) and run commands or copy files. Use when asked to check, fix, inspect or prepare something on the server — container status, logs, disk, the /opt/<stack> directories, a failed deploy's aftermath — or when a GitHub Actions deploy job needs a one-time step done on the box.
---

# Running commands on the production VPS

One Vultr VPS (`hostname bridge`, Ubuntu 24.04) runs both product stacks as
docker compose projects, plus the shared TLS/routing edge stack:

| Path | What |
| --- | --- |
| `/opt/bridge_leads` | lead/contract app — `docker-compose.prod.yml` + `.env` + `data/queries.db` |
| `/opt/bridge_play` | play solver — same layout, own compose file and query log |
| `/opt/edge` | Caddy edge (TLS, vhosts); **owned by the FBO repo's `deploy/edge/`**, not this one |

Deploys happen from GitHub Actions (`.github/workflows/deploy.yml`) over the
same SSH access: `scp-action` copies the stack's compose file into `/opt/<stack>`,
then `ssh-action` runs `docker compose pull && up -d` there. Nothing on the box
is hand-edited in the normal course of things — this skill is for the
exceptions.

## Access

- User **`deploy`** (uid 1001; in `docker` and `sudo` groups, **passwordless
  sudo** via `/etc/sudoers.d/deploy`). Root SSH login is disabled.
- Key auth only; the user's `~/.ssh/id_ed25519` is authorised, so from this
  machine a plain `ssh deploy@<host>` works with no prompt. (`gha_deploy_key`
  in `~/.ssh` is the *Actions* key — don't use it interactively.)
- The address is **not recorded in the repo** (same convention as the
  `query-log` skill). Read it from `$BRIDGE_VPS` (`deploy@<ip>`), and if that's
  unset, ask the user — never guess an IP.

Always run non-interactively so a missing key or host-key prompt fails fast
instead of hanging the tool call:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 "$BRIDGE_VPS" 'hostname; id'
```

(`$BRIDGE_VPS` in the Bash tool; `$env:BRIDGE_VPS` in PowerShell.)

## Ground rules

This is production. Before anything that **changes** the box (mkdir/chown,
editing files under `/opt`, `docker compose up/down/restart`, pruning,
package installs), say what you're about to run and why. Read-only inspection
(`ls`, `docker ps`, `docker logs`, `df`, `cat` of a compose file) needs no
ceremony. Never `docker compose down` a stack, delete `data/`, or touch
`/opt/edge` unless the user asks for exactly that — `/opt/edge` in particular
is managed from another repo and any edit here will be overwritten and may take
both sites offline.

Prefer one `ssh` call with a `set -e` script over many round-trips, and quote
the remote script in single quotes so `$` expands on the box, not locally:

```bash
ssh -o BatchMode=yes "$BRIDGE_VPS" 'set -e; cd /opt/bridge_play; docker compose -f docker-compose.prod.yml ps'
```

## Common jobs

**Is the stack up / what is it running?**

```bash
ssh -o BatchMode=yes "$BRIDGE_VPS" 'docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"'
ssh -o BatchMode=yes "$BRIDGE_VPS" 'cd /opt/bridge_leads && docker compose -f docker-compose.prod.yml logs --tail 100 backend'
```

**A `deploy-*` job failed at `create folder /opt/<stack>` (`Process exited with
status 1` in scp-action).** `/opt` is root-owned and the workflow's SSH user is
`deploy`, so the stack directory must exist and be owned by `deploy` *before*
the first deploy — `deploy/provision.md` step 4. Create it, then re-run the
workflow:

```bash
ssh -o BatchMode=yes "$BRIDGE_VPS" 'sudo mkdir -p /opt/bridge_play && sudo chown deploy:deploy /opt/bridge_play && ls -ld /opt/bridge_*'
```

**Pin or unpin a stack's image tag** (`deploy/.env.example`): edit
`/opt/<stack>/.env`, then re-run the deploy job for that stack (or `docker
compose -f docker-compose.prod.yml up -d` there). A deploy run's `image_tag`
input overrides the file for that run only.

**Copy a file down** (never edit the live copy): `scp "$BRIDGE_VPS":/opt/bridge_leads/data/queries.db ./` —
but for the query log use the `query-log` skill, which does exactly this and
decodes the rows.

**Disk / memory pressure** (the box is 2 vCPU / 4 GB and DDS is memory-hungry
per thread):

```bash
ssh -o BatchMode=yes "$BRIDGE_VPS" 'df -h / ; free -m ; docker system df'
```

`docker image prune -f` is safe (the deploy job runs it anyway); `docker
system prune` with volumes is not — the query logs are bind mounts, but don't
make that the thing you find out.

## After changing something

Say what changed on the box in plain terms, and whether it needs a matching
change in the repo (usually `deploy/provision.md`, so a rebuild of the VPS
reproduces it). One-off fixes that only live on the server are how provisioning
docs drift.
