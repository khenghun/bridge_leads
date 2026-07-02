# VPS provisioning — one-time setup

Stands up the production stack on a fresh Vultr VPS. After this, all deploys
happen through the GitHub Actions **deploy** job (manual `workflow_dispatch`);
you should never need to rebuild or edit anything on the box.

Prereqs (user accounts):

- Vultr **High Frequency** instance, 2 vCPU / 4 GB, **Ubuntu 24.04 LTS**.
- A domain with an `A` record `<yourdomain>` → the VPS IP (add `www` too if
  wanted — but the Caddyfile currently serves the apex only). Let DNS
  propagate before first boot of the stack, or Caddy's cert issuance will
  retry until it does.

All commands below run on the VPS as root (Vultr's default login) unless noted.

## 1. Create the deploy user

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy          # optional: sudo for maintenance
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/   # or paste your pubkey
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
```

Generate a **separate keypair for GitHub Actions** (on your own machine):

```bash
ssh-keygen -t ed25519 -f gha_deploy_key -N "" -C "gha-deploy"
```

Append `gha_deploy_key.pub` to `/home/deploy/.ssh/authorized_keys` on the VPS.
The **private** key becomes the `VPS_SSH_KEY` GitHub secret (step 6).

Then harden sshd — in `/etc/ssh/sshd_config` (or a drop-in under
`sshd_config.d/`):

```
PermitRootLogin no
PasswordAuthentication no
```

```bash
systemctl restart ssh
```

(Verify you can `ssh deploy@<ip>` from a second terminal **before** closing
your root session.)

## 2. Firewall + fail2ban

```bash
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp
ufw --force enable
apt-get update && apt-get install -y fail2ban   # default jail covers sshd
```

(443/udp is HTTP/3; harmless to skip, small win to allow.)

## 3. Install Docker Engine + compose plugin

Official convenience script (fine for a single-purpose box):

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
```

Log out/in as `deploy` for the group to take effect. Everything from here runs
as **deploy**.

## 4. App directory + config

```bash
sudo mkdir -p /opt/bridge_leads && sudo chown deploy:deploy /opt/bridge_leads
cd /opt/bridge_leads
```

Copy `docker-compose.prod.yml` and `Caddyfile` from the repo into
`/opt/bridge_leads/` (scp them, or just `git clone` and `cp` — the deploy
workflow re-copies them on every deploy anyway, so drift self-heals).

Create `/opt/bridge_leads/.env` (see `deploy/.env.example`):

```
DOMAIN=yourdomain.example
# IMAGE_TAG=latest   # pin a commit SHA here to hold the stack at a version
```

## 5. Registry access

GHCR images are **private by default** after the first CI push. Pick one:

- **Make them public** (simplest, fine for this app): on GitHub → your
  profile → Packages → `bridge_leads-backend` / `-frontend` → Package
  settings → Change visibility → Public. No login needed on the VPS.
- **Keep private**: create a classic PAT with `read:packages` only, then on
  the VPS: `docker login ghcr.io -u khenghun` (paste the PAT as password).

Note: images exist only after the workflow has run once — push to `main`
first if `docker compose pull` reports "not found".

## 6. GitHub Actions secrets

Repo → Settings → Secrets and variables → Actions:

| Secret        | Value |
| ------------- | ----- |
| `VPS_HOST`    | VPS public IP (or hostname) |
| `VPS_USER`    | `deploy` |
| `VPS_SSH_KEY` | contents of `gha_deploy_key` (the private key from step 1) |

## 7. First launch

```bash
cd /opt/bridge_leads
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f caddy   # watch cert issuance
```

Caddy obtains the Let's Encrypt cert on first boot (needs DNS already
pointing here). Certs persist in the `caddy_data` volume.

## 8. Verify

- `https://<yourdomain>` loads the app with a valid cert; `http://` redirects.
- `curl https://<yourdomain>/api/health` → ok.
- Run a real simulation in the UI (confirms DDS/libgomp1 in the pulled image).
- `sudo reboot`, wait, confirm the stack came back by itself
  (`restart: unless-stopped`).
- GitHub → Actions → **Build & Deploy** → Run workflow (leave tag `latest`) —
  confirms the CI deploy path end to end.

## Routine operations

| Task | How |
| ---- | --- |
| Deploy latest `main` | Actions → Build & Deploy → Run workflow |
| Roll back | Run workflow with `image_tag` = an older commit SHA |
| Logs | `docker compose -f docker-compose.prod.yml logs -f [backend\|frontend\|caddy]` |
| OS updates | `sudo apt-get update && sudo apt-get upgrade` (occasionally; reboot if kernel) |
