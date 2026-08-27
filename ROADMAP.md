# Roadmap

Two products, one repo. Each has its own version line, roadmap, plan docs and
changelog:

| Product | Roadmap | Plan docs | In-app changelog (source of truth) |
| --- | --- | --- | --- |
| Opening Lead Simulator & Optimal Contract Calculator (`v2.2`) | [`docs/lead/ROADMAP.md`](docs/lead/ROADMAP.md) | `docs/lead/` | `frontend/src/apps/changelog/releases.ts` |
| Play Solver (`v1.0`, in progress) | [`docs/play/ROADMAP.md`](docs/play/ROADMAP.md) | `docs/play/` | `frontend/src/apps/play/changelog/releases.ts` |

Why one repo, and what the products share (engine, frontend components, the
backend image) versus what stays separate (versions, images, deploy stacks,
domains): [`docs/two-products-one-repo.md`](docs/two-products-one-repo.md).

## Repo-level milestones

- **2026-08-27 — two-product layout.** Per-stack compose files under
  `deploy/<stack>/`, per-product frontend builds (`build:lead` / `build:play`,
  `ARG APP`), CI runs both test suites before building and deploys per stack
  via a `stack` dispatch input. Verified in production with zero behaviour
  change for the live app, rollback re-proved.

> **Session handoff:** work-in-progress state is kept in `latest_updates.md`,
> a local, gitignored scratch file. Anything worth keeping belongs in the
> product roadmaps.
