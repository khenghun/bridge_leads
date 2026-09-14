# VPS provisioning — one-time setup

Stands up the production stack on a fresh Vultr VPS. After this, all deploys
happen through the GitHub Actions **deploy** job (manual `workflow_dispatch`);
you should never need to rebuild or edit anything on the box.

Prereqs (user accounts):

- Vultr **High Frequency** instance, 2 vCPU / 4 GB, **Ubuntu 24.04 LTS**.
- A domain with an `A` record `<yourdomain>` → the VPS IP (add `www` too if
  wanted — but the Caddyfile serves exactly the one host in `DOMAIN`; a
  subdomain like `bridge-leads.<domain>` works the same way). Let DNS
  propagate before first boot of the stack, or Caddy's cert issuance will
  retry until it does. Registrar gotchas (Porkbun): leave the Host field
  **blank** for the apex (don't type `@`), and delete the pre-created parking
  `ALIAS` + wildcard `CNAME` records or they mask yours.

All commands below run on the VPS as root (Vultr's default login) unless noted.

## 1. Create the deploy user

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy          # optional: sudo for maintenance
# --disabled-password means sudo could never prompt successfully; if deploy
# should sudo (recommended — root SSH gets disabled below), make it
# passwordless:
echo 'deploy ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/deploy && chmod 440 /etc/sudoers.d/deploy
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

One directory per product stack, owned by `deploy`. `/opt` itself is
root-owned, and the deploy workflow's `scp-action` runs as `deploy` and does
**not** sudo — if a stack's directory is missing it fails at
`create folder /opt/bridge_play` with `Process exited with status 1`. So this
step is required before the *first* deploy of each stack (the lead stack got it
at initial provisioning; the play stack was added later and needs it too):

```bash
sudo mkdir -p /opt/bridge_leads /opt/bridge_play
sudo chown deploy:deploy /opt/bridge_leads /opt/bridge_play
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

`VPS_SSH_KEY` gotcha: paste the **whole file** — `-----BEGIN/END OPENSSH
PRIVATE KEY-----` lines included — **with a trailing newline** after the END
line. A missing final newline (or a clipboard tool mangling line endings —
open the key in Notepad and Ctrl+A/Ctrl+C rather than piping to `clip`) makes
the deploy job fail with `ssh.ParsePrivateKey: ssh: no key found`.

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

## 9. Play worker (AWS Lambda) — one-time setup

Play v1.5 fans the expert filter's judgements out to a Lambda function
(`docs/play/v1.5-lambda-strict-plan.md`). The image is built and pushed by
CI (`build-worker`), the function code is updated by CI (`deploy-worker`),
and the pieces below are created once by hand. **No AWS identifier goes in
the repo** — account id, ECR URI, role ARNs and keys live only in GitHub
secrets and in `/opt/bridge_play/.env`. Everything is in `ap-southeast-1`.
The AWS CLI is not needed on any machine of yours: the GitHub runner has it,
the VPS uses boto3.

Console (IAM / ECR), already done 2026-09-10/11 — listed so the names match:

| Item | Setting |
| --- | --- |
| ECR private repository | `bridge-play-worker` (mutable tags) |
| OIDC identity provider | `token.actions.githubusercontent.com`, audience `sts.amazonaws.com` |
| Deploy role `bridge-play-deploy` | custom trust policy on that provider for `repo:khenghun/bridge_leads:*`; inline policy `bridge-play-deploy-policy`: `ecr:GetAuthorizationToken` + push on the one repo, `lambda:UpdateFunctionCode` / `GetFunction` / `GetFunctionConfiguration` on `function:bridge-play-worker` |
| Execution role `bridge-play-worker-role` | `AWSLambdaBasicExecutionRole` only |
| Lambda concurrency quota | request an increase if the account shows 50 (new accounts do): Service Quotas → AWS Lambda → *Concurrent executions* → Request increase (1 000). Check the **applied** value on the quota row afterwards, the request history only says "Case Closed" (this account: 1 000 applied, verified 2026-09-14) |
| Lambda memory cap | new accounts are capped at **3008 MB** per function (the console rejects more with `'MemorySize' ... less than or equal to 3008`). Not a Service Quotas entry — open a **support case**: Support Center → describe the issue → *Create a case* → subject "Raise maximum Lambda function memory to 10240 MB in ap-southeast-1", description = the function name, that it is CPU-bound and vCPUs scale with memory, low traffic. Free on Basic Support; granted within three days on this account (2026-09-11 → by 2026-09-14). Until then run the function at 3008 MB (≈ 1.7 vCPU); once granted, edit memory to 7076 MB and the save just succeeds |

Then, in this order:

1. **GitHub secret** — Repo → Settings → Secrets and variables → Actions:

   | Secret | Value |
   | --- | --- |
   | `AWS_DEPLOY_ROLE_ARN` | the ARN of `bridge-play-deploy` (IAM → Roles → the role → *ARN*) |

   Nothing else: the ECR registry host is read from the role at run time and
   the region is fixed in the workflow.
2. **First image push** — push to `main` (or Actions → *Test, Build & Deploy*
   → Run workflow, stack `worker`). The `build-worker` job pushes
   `bridge-play-worker:latest` and `:<sha>`; `deploy-worker` reports that the
   function does not exist yet and succeeds.
3. **Create the function** — Lambda → Create function → *Container image*:
   name `bridge-play-worker`, image = browse ECR → `bridge-play-worker:latest`,
   architecture x86_64, execution role = existing `bridge-play-worker-role`.
   Then Configuration → General: memory **7076 MB** (four vCPUs for the four
   DDS threads; **3008 MB** while a fresh account's cap stands), timeout **60 s**,
   ephemeral storage default. The create wizard leaves the timeout at 3 s,
   which a cold start exceeds — `Task timed out after 3.00 seconds` means
   this step was skipped. Environment variables:
   `BRIDGE_DDS_THREADS=4` (schedule parity — the worker's health check
   reports `schedule_ok`). No function URL, no trigger, provisioned
   concurrency off.
4. **Prove it** — Test tab, event `{"op": "health"}`: expect `ok: true`,
   `schedule_ok: true`, `dds_threads: 4`, a `solve_ms` in the tens, and
   `engine_sha` equal to the API's (`python -c "from engine.version import
   engine_sha; print(engine_sha())"` in the same image). A failure here is
   the DDS `.so` not loading under the Lambda runtime. Then
   `{"op": "bench", "boards": 200, "seed": 0, "engine_sha": "<that sha>"}`
   for the per-vCPU speed; run the same op in-process on the laptop and the
   VPS to compare.
5. **Invoke-only user for the VPS** — IAM → Users → `bridge-play-invoker`, no
   console access, inline policy allowing only `lambda:InvokeFunction` on the
   function's ARN. Create an access key (*Application running outside AWS*)
   and add to `/opt/bridge_play/.env`:

   ```
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   AWS_DEFAULT_REGION=ap-southeast-1
   BRIDGE_WORKER_FUNCTION=bridge-play-worker
   BRIDGE_JUDGE_BACKEND=local     # flip to lambda when the v1.5 client ships
   ```
6. **Billing alert** (optional) — Billing → Budgets, a few dollars a month.

From then on every play deploy (`stack: play`) updates the function to the
same tag as the API; `stack: worker` updates the function alone; rollback is
the same `image_tag` input as the stacks.

## Routine operations

| Task | How |
| ---- | --- |
| Deploy latest `main` | Actions → Build & Deploy → Run workflow |
| Roll back | Run workflow with `image_tag` = an older commit SHA |
| Logs | `docker compose -f docker-compose.prod.yml logs -f [backend\|frontend\|caddy]` |
| Query log | From your own machine: `BRIDGE_VPS=deploy@<ip> python scripts/view_queries.py --summary` (copies the DB down and decodes it; `--help` for filters). On the box: `sqlite3 /opt/bridge_leads/data/queries.db 'SELECT ts, tool FROM queries ORDER BY id DESC LIMIT 20'`. One row per simulation (timestamp, tool, request body). Unset `BRIDGE_QUERY_LOG` in the compose file to turn it off. Bind-mounted, so it survives image pulls; back it up by copying the file. |
| OS updates | `sudo apt-get update && sudo apt-get upgrade` (occasionally; reboot if kernel) |
