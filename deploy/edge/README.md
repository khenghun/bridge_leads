# Shared edge — TLS and routing for every app on the VPS

`compose.yaml` + `Caddyfile` here are the source of truth for `/opt/edge` on
the VPS. Caddy is the only container publishing 80/443; each app stack
publishes no ports, joins the external `edge` docker network and gets one
site block in the Caddyfile that proxies to that stack's network alias.

| Hostname | Upstream alias | Stack |
| --- | --- | --- |
| `bridge-leads.icycookie.xyz` | `bl-backend:8000` (`/api/*`), `bl-frontend:80` | `deploy/lead/` → `/opt/bridge_leads` |
| `bridge-play.icycookie.xyz` | `bp-backend:8000` (`/api/*`), `bp-frontend:80` | `deploy/play/` → `/opt/bridge_play` |
| `kk-relay.icycookie.xyz` | `kk-frontend:80` | `deploy/kk_relay/` → `/opt/kk_relay` |

History: the edge was extracted from the lead stack's own Caddy on
2026-08-16 and lived in the FBO repo (`bbov2/deploy/edge/`) while that
project shared the box. FBO was retired on 2026-10-16 and the files moved
here unchanged apart from dropping its site block; the FBO test stack's
containers (`/opt/fbo-test`, stopped since 2026-09-01) were left in place.

## Adding or changing a site block

1. DNS first: an `A` record for the new hostname → the VPS IP (Porkbun: host
   field is the bare label, e.g. `kk-relay`, no `@`). Caddy issues the
   Let's Encrypt cert on the first load of the block and retries in a loop
   if the name does not resolve here yet.
2. Edit `Caddyfile` **in this repo** and commit.
3. Actions → *Test, Build & Deploy* → Run workflow, stack **`edge`**. The job
   copies `Caddyfile` + `compose.yaml` to `/opt/edge`, runs `caddy validate`
   inside the container and reloads only if that passes — a typo leaves the
   running config untouched. By hand, the same thing is:

   ```bash
   cd /opt/edge
   docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
   docker compose exec caddy caddy reload   --config /etc/caddy/Caddyfile
   ```

The VPS copy is disposable; this repo is the source of truth.

Gotcha (2026-10-16): the Caddyfile must reach the container through a
**directory** mount (`.:/etc/caddy:ro`). The original single-file mount
pinned the inode, so the file scp put in place was never seen inside the
container and the reload said `config is unchanged` while the host file had
the new block. If a reload ever claims no change after an edit, compare
`docker compose exec caddy grep -c <host> /etc/caddy/Caddyfile` with the
host file.

## Rebuilding the edge from nothing

```bash
docker network create edge          # once
sudo mkdir -p /opt/edge && sudo chown deploy:deploy /opt/edge
# copy compose.yaml + Caddyfile there (the edge deploy job does this)
cd /opt/edge && docker compose up -d && docker compose logs -f caddy
```

Certs live in the `edge_caddy_data` volume and survive `up -d`; a fresh
volume means fresh issuance, which takes seconds when DNS already points
here. Never `docker compose down` the edge on a whim — it takes every site
offline at once.
