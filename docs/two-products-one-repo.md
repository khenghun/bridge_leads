# Two products, one repo

The architecture decisions behind hosting two products — the **lead/contract
simulator** and the **play solver** — in one repository, and the migration
that made room for the second. Each product has its own version line, its own
`docs/<product>/` folder with a `ROADMAP.md`, its own changelog in the UI, its
own image tags and deploy job. The repo is shared for one reason: they use the
same engine and the same frontend components.

Status: the migration ("Milestone 1" below) is **complete and verified in
production, 2026-08-27**. The play solver's own design and history live in
`docs/play/` (`v1.0-play-solver-plan.md`, `ROADMAP.md`).

## The shape of the thing

The play solver is a different product, not a fourth tab. The two existing
tools are the same interaction — fill a form, run a Monte-Carlo + DDS
simulation, read a ranked table — which is why they share one app shell, one
MP/IMP toggle, one changelog. The play solver is a different interaction:
load a hand you already played, step through it, and read a grade for every
decision — a viewer with a solver behind it, not a form. Different UX,
different pacing, different audience framing. So:

- **Separate domain**, with plain hyperlinks between the two apps. Nothing
  carries across origins (no shared localStorage or mode preference); anything
  that must travel — "open this deal in the play solver" — goes in the URL.
- **Same repo.** Both products want `engine/dds_runtime`, the card/PBN
  vocabulary, `HandEntry`, `DealDiagram`, `lib/bridge.ts`. A second repo means
  copy-paste drift or publishing internal packages; neither is worth it.
- **Independent deploys.** Two compose stacks on the VPS, two dispatch deploy
  jobs, per-stack image tags. Because each image snapshots the shared code at
  its build commit, "lead runs engine-as-of-A, play runs engine-as-of-B" is a
  supported state, not skew — that is what makes independent versioning safe
  in a monorepo.

## Why one backend image, two containers

Mounting play routes into `app/main.py` would make every play deploy redeploy
the lead API — the "two deploy jobs" would be an illusion. So play gets its own
FastAPI app (`backend/app_play/`) and its own container.

But it does **not** get its own image. One backend image carries both app
packages plus the shared `engine/`; the lead container runs the default `CMD`
(`uvicorn app.main:app`), the play container overrides `command:` in its
compose file. Same image repo, independently chosen tags per stack — 90% of
the value of two images with none of the build cost, and rollback tags stay
continuous.

Two containers also means two DDS processes, each with its own `DDS_LOCK` and
the full thread allowance (`BRIDGE_DDS_THREADS=2`, the max on the 2-vCPU box).
There is no cross-product queue: a play solve running while a lead batch runs
contends for CPU at the OS level and both grind. Accepted deliberately — the
tools will rarely be used simultaneously, and an interactive play solve is a
single-deal `solve_board`, not a 300-deal batch.

## Why one frontend project, two images

Two Vite projects cannot share `components/` and `lib/bridge.ts` without
workspace machinery. Instead: one `frontend/` source tree, one entry per
product, and the Docker build selects which to build via a build arg
(`ARG APP=lead|play` → `npm run build:${APP}`). Shared code stays plain
relative imports. npm workspaces only if the two apps' dependency sets ever
genuinely diverge.

Each product image carries its own `nginx.conf` (proxy target and timeouts
differ) and the play app gets its own What's-new equivalent — sharing one
changelog across two domains would recouple what the split decouples.

## CI: test together, deploy apart

- **One test job**, always, for everything. A change to `engine/sampling.py`
  must run every consumer's tests; splitting tests per product would defeat
  the purpose of the monorepo. (This job is new — CI previously built without
  testing.)
- **One build job** producing all images on every main push, tagged
  `:latest` + `:sha` as before. Image names are grandfathered
  (`bridge_leads-backend` becomes the shared backend image) because renaming
  GHCR repos orphans rollback tags.
- **Per-stack deploy jobs**, dispatch-gated as today, selected by a `stack`
  input. Per-stack compose files live under `deploy/<stack>/` in the repo and
  land in `/opt/bridge_leads` and `/opt/bridge_play` on the VPS.

## Versioning, docs, releases: per product

| | Lead / contract simulator | Play solver |
| --- | --- | --- |
| Version line | `v1.0 … v2.2` | `v1.0 …` (its own count) |
| Source of truth | `frontend/src/apps/changelog/releases.ts` | `frontend/src/apps/play/changelog/releases.ts` |
| Roadmap + plan docs | `docs/lead/` | `docs/play/` |
| Frontend build | `npm run build:lead` (`APP=lead`) | `npm run build:play` (`APP=play`) |
| Images | `bridge_leads-backend`, `bridge_leads-frontend` | `bridge_leads-backend` (shared, play `command:`), `bridge_play-frontend` |
| Deploy | `deploy/lead/`, job `deploy-lead`, `/opt/bridge_leads` | `deploy/play/`, job `deploy-play`, `/opt/bridge_play` |

The backend image is shared because both apps sit on the same `engine/`;
each stack pins its own tag of it, so their backend versions still move
independently. Nothing else is shared at release time.

## Milestone 1 — migrate the existing solver (zero behavior change)

When this lands, the live site serves exactly what it serves today, from the
same image names, same domain, same VPS directory. No `releases.ts` entry —
nothing here is player-visible.

Phase 1, repo changes:

| Change | Why |
| --- | --- |
| `docker-compose.prod.yml` → `deploy/lead/docker-compose.prod.yml` (contents unchanged) | the repo-root location cannot scale to two stacks; the VPS path (`/opt/bridge_leads`) stays put |
| `.github/workflows/deploy.yml`: scp source follows the move (`strip_components` so it lands flat) | keeps every commit deployable; the rest of the CI restructure is Phase 2 |
| `frontend/package.json`: `build` → alias for new `build:lead` | the parameterizable name the Docker build arg selects |
| `frontend/Dockerfile`: `ARG APP=lead`, `RUN npm run build:${APP}` | proves the two-image mechanism now, while only one app exists |
| `backend/Dockerfile`: fix stale comment (`engine/lead_simulator.py` → `engine/dds_runtime.py`) | drive-by correctness |

Phase 2, CI restructure: add the `test` job (backend pytest + frontend vitest;
`tsc -b` already rides in the frontend image build), gate `build` on it, rename
`deploy` → `deploy-lead`, add the `stack` dispatch choice.

Phase 3, verify: dispatch a lead deploy at `latest`, confirm the site is
unchanged (one lead sim, one contract sim, query log gains rows); dispatch once
at the previous good SHA to prove rollback survived the migration; roll
forward.
