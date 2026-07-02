# v5 detailed plan — Production deployment: Vultr VPS + Caddy + GHCR CI/CD

High-level status lives in `../ROADMAP.md`. This stage takes the **unchanged**
v4 container stack and stands it up on a public host with TLS and a
push-button deploy pipeline. **No application code changes** — only new infra
files (`docker-compose.prod.yml`, `Caddyfile`, a GitHub Actions workflow) and a
one-time VPS provisioning procedure.

Status: **infra files written** (`docker-compose.prod.yml`, `Caddyfile`,
`.github/workflows/deploy.yml`, `deploy/provision.md`, `deploy/.env.example`);
awaiting domain + VPS provisioning. Repo is `github.com/khenghun/bridge_leads`,
so images are `ghcr.io/khenghun/bridge_leads-{backend,frontend}`.

Deviations from the sketch below, decided at implementation time:
- The deploy job also **scp-syncs `docker-compose.prod.yml` + `Caddyfile`** to
  the VPS before restarting, so the box never drifts from the repo.
- Rollback is a `workflow_dispatch` **`image_tag` input** (a commit SHA),
  passed as `IMAGE_TAG` to compose; the VPS `.env` can pin it persistently.
- `BRIDGE_DDS_THREADS=2` in prod (2-vCPU box), not 4.
- Caddy also publishes `443/udp` (HTTP/3).

---

## Goals

- Serve the app at `https://<yourdomain>` from a Vultr VPS.
- Automatic TLS (Let's Encrypt) with zero manual cert wrangling.
- Images built in CI and stored in a registry; the VPS only **pulls** — it never
  compiles (a fresh build is ~260 s of pip alone plus the Vite build).
- CI/CD via GitHub Actions: **build+push on every `main` commit**, but the actual
  **VPS deploy is manual** (a `workflow_dispatch` button) so production only
  changes when a human clicks.

## Decisions (locked)

| Concern        | Choice                    | Why |
| -------------- | ------------------------- | --- |
| Host           | **Vultr High Frequency VPS**, 2 vCPU / 4 GB | DDS is CPU- and single-thread-sensitive; High Frequency beats Regular Cloud Compute. Room to size up later. |
| TLS / edge     | **Caddy** container on the VPS | Auto-issues + renews Let's Encrypt certs; self-contained, no third-party dependency. |
| Registry       | **GitHub Container Registry** (`ghcr.io`) | Free for this usage, lives next to the repo, CI auth via the built-in `GITHUB_TOKEN`. |
| Deploy trigger | **Manual only** (`workflow_dispatch`) | Build/push is automatic on `main`; the deploy step is a human-gated button. |

## Target topology

```
git push main ──► GitHub Actions [build job] ──► push images to ghcr.io
                                                        │
   (click "Run workflow" ──► [deploy job, workflow_dispatch] ──► SSH to VPS)
                                                        │
                                              docker compose pull && up -d
                                                        │
Browser ──► https://<domain> ──► VPS :443 ──────────────┘
                                     │
                              ┌──────┴───────────────────────────┐
                              │  caddy    :80→:443  (auto-TLS)    │
                              │    ├─ /api/*  → backend:8000      │
                              │    └─ /       → frontend:80       │
                              │  frontend  nginx  (static SPA)    │
                              │  backend   uvicorn (FastAPI+DDS)  │
                              └───────────────────────────────────┘
                                   docker network · restart: unless-stopped
```

Only Caddy publishes ports (80/443). `frontend` and `backend` are reachable
only on the internal compose network.

## New files

### `docker-compose.prod.yml`

Production compose, used with `-f docker-compose.prod.yml`. Differs from the dev
`docker-compose.yml`:

- **`caddy`** service — `caddy:2-alpine`; ports `80:80` and `443:443`; mounts
  `./Caddyfile:/etc/caddy/Caddyfile:ro` and named volumes `caddy_data` (certs)
  and `caddy_config`; `restart: unless-stopped`; `depends_on: [frontend, backend]`.
- **`frontend` / `backend`** — replace `build:` with
  `image: ghcr.io/khenghun/bridge_leads-frontend:latest` /
  `...-backend:latest`; **remove** the public `ports:` mapping (Caddy fronts
  them); keep `backend`'s `BRIDGE_DDS_THREADS`; add `restart: unless-stopped` to
  both. `expose:` internal ports only.

Open item — **who terminates `/api`.** Today the frontend's `nginx.conf` proxies
`/api` → `backend:8000`. Two options:
1. **Caddy routes `/api` directly to `backend`** (preferred) — nginx serves only
   static files, Caddy owns all routing. Cleaner separation.
2. Keep nginx proxying `/api`; Caddy forwards everything to `frontend`. Fewer
   changes but two layers of `/api` proxying.
Plan of record: **option 1**, so `nginx.conf` can drop its `/api` block later
(optional cleanup, not required for v5).

### `Caddyfile`

```
<yourdomain> {
    encode gzip
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle {
        reverse_proxy frontend:80
    }
}
```

Domain hardcoded (or via env). Caddy provisions the cert on first boot once DNS
resolves to the VPS. `www` → apex redirect can be added later.

### `.github/workflows/deploy.yml`

Two jobs:

- **build** — triggers: `push` to `main` **and** `workflow_dispatch`. Uses
  `docker/login-action` (registry `ghcr.io`, `GITHUB_TOKEN`),
  `docker/build-push-action` for `./backend` and `./frontend`. Tags each image
  `latest` **and** `${{ github.sha }}` (immutable tag = rollback handle). Push to
  `ghcr.io/khenghun/bridge_leads-{backend,frontend}`.
- **deploy** — trigger: `workflow_dispatch` **only**. `appleboy/ssh-action` into
  the VPS runs, in the app dir:
  ```
  docker compose -f docker-compose.prod.yml pull
  docker compose -f docker-compose.prod.yml up -d
  docker image prune -f
  ```
  Rollback = re-run with an older SHA tag (via an input, or by pinning
  `IMAGE_TAG` in the VPS `.env`).

### GitHub secrets

| Secret        | Purpose |
| ------------- | ------- |
| `VPS_HOST`    | VPS public IP / hostname |
| `VPS_USER`    | non-root `deploy` user |
| `VPS_SSH_KEY` | private key for that user |

Registry auth in CI uses the built-in `GITHUB_TOKEN` (no secret needed). GHCR
images default to private; either keep them private (VPS logs in with a
read-only PAT) or make them public (VPS pulls unauthenticated).

## VPS provisioning (one-time)

A documented checklist / script (`deploy/provision.sh` or in this doc):

1. Create the Vultr instance (High Frequency, 2 vCPU / 4 GB, Ubuntu LTS).
2. `A` record `<domain>` → VPS IP (and `www` if wanted). Wait for DNS.
3. Create non-root `deploy` user; add your SSH pubkey; disable password/root SSH.
4. `ufw` allow `22/tcp`, `80/tcp`, `443/tcp`; enable. Install `fail2ban`.
5. Install Docker Engine + compose plugin.
6. `docker login ghcr.io` with a **read-only** PAT (only if images stay private).
7. Copy `docker-compose.prod.yml` + `Caddyfile` (+ `.env` with domain / image
   tag) to the app dir.
8. `docker compose -f docker-compose.prod.yml up -d` — Caddy fetches the cert.

Thereafter, deploys are the manual GitHub Actions `deploy` job only.

## Sequencing & ownership

| # | Step | Owner |
| - | ---- | ----- |
| 1 | Buy domain, create Vultr VPS, set `A` record | **user** (accounts) |
| 2 | Write `docker-compose.prod.yml`, `Caddyfile`, `deploy.yml` | Claude |
| 3 | Write VPS provisioning script/checklist | Claude |
| 4 | Add GitHub secrets, one-time provision the VPS | **user** (+ Claude guidance) |
| 5 | First manual `workflow_dispatch` deploy; verify `https://` + `/api/health` | joint |

Steps 2–3 need only the GitHub `<owner>` name and can be done before the VPS
exists. Steps 1, 4 need the user's Vultr/GitHub accounts.

## Verification

- **DNS/TLS** — `https://<domain>` loads with a valid Let's Encrypt cert; HTTP
  redirects to HTTPS (Caddy default).
- **Routing** — `GET /api/health` returns ok through Caddy; a real
  `POST /api/simulate` returns ranked leads (confirms `libgomp1` + DDS work in
  the pulled image, same as the local `docker compose up` check).
- **CI/CD** — a `main` commit produces new `latest` + SHA tags in GHCR; the
  manual `deploy` run pulls and restarts with zero code rebuild on the box.
- **Resilience** — `docker compose restart` / VPS reboot brings the stack back
  (`restart: unless-stopped`).

## Out of scope (later)

- Multi-replica / horizontal scaling; the single VPS is sized for expected load.
- Observability (metrics/log aggregation), rate limiting, auth.
- Blue/green or zero-downtime deploys — brief restart blip is acceptable here.
- Staging environment separate from prod.
