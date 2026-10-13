# Deployment Guide — Pokemon Price Tracker

**Server:** Hetzner CX23 at `65.21.178.63`
**OS:** Ubuntu 24.04
**App path:** `/opt/pokemon`
**App port:** 8502 (Streamlit)
**Repo:** `https://github.com/Mitanoooo/pokemon.git`

## GitHub authentication (git push from the EC2 dev machine)

Global `~/.gitconfig` is the company identity and must never carry a `github.com` credential helper or a `user.*` override for this account. Mitanoooo repos authenticate through repo-local config only:

```bash
git config --local credential.https://github.com.helper 'store --file=/home/ec2-user/.git-credential-mitanoooo-store'
```

The store file holds a Mitanoooo-owned PAT (`repo` scope) as `https://Mitanoooo:<PAT>@github.com`, chmod 600. Remote URLs must not embed a token: an embedded token bypasses credential helpers. New Mitanoooo repos are cloned with `~/mitanoooo/bin/mito-clone`, which sets all of this. See `~/mitanoooo/README.md`.

To rotate the PAT, replace the store file contents. Do not use the shared `$GITHUB_TOKEN` env var, which resolves to the company account.

---

> **SSH is blocked by corporate firewall.** There is no SSH access from the office network. Deploys from that network go through the pokemon-scoped HTTP deploy hook below — SSH was only ever needed once, from a machine outside the office network, to do the initial bootstrap (already done). Sessions/automation that already have `~/.ssh/pokemon-hetzner` installed (outside the office network) can instead deploy via direct SSH — see "Deploying via direct SSH" below, which is the method actually used day-to-day so far.

> **Shared server.** The drafter app runs on this server too (Streamlit on 8501, Caddy on port 80, upload server on 9000). The pokemon app runs on port 8502 and is reachable at `http://65.21.178.63/pokemon/`. Drafter owns `/etc/caddy/Caddyfile`, which imports `/etc/caddy/routes.d/*.caddy` ahead of its catch-all route; pokemon owns `routes.d/pokemon.caddy`, protected by Caddy `basicauth` (username `pokemon`, password in `/root/pokemon-basicauth.txt` on the server; never store it in this repo).

**Status: deployed and live.** The app went live on 2026-08-10 and the tracker refocus landed on 2026-09-02. The database is the four tables of the refocus: `sites`, `scrape_runs`, `listings`, `updates`.

**Data loss on 2026-10-13.** A drafter rebuild (Hetzner `actions/rebuild`) wiped the server's root disk, which then held everything pokemon had: code, database, `.env`, deploy token, systemd units, crontab and the Caddy route. Hetzner backups were off and no snapshot existed, so the database (including the archived pre-refocus price readings) is gone. The app was reinstalled the same day on an empty database.

## What survives a server rebuild

A rebuild reinstalls Ubuntu on the root disk. Only the Hetzner volume `drafter-data` (`/mnt/drafter-data`) survives, so pokemon keeps its state there:

| Path on the volume | Linked from | Owner |
|---|---|---|
| `pokemon/pokemon.db` | `/opt/pokemon/pokemon.db` | `pokemon` |
| `pokemon/.env` | `/opt/pokemon/.env` | `pokemon`, mode 600 |
| `pokemon/secrets/deploy.token` | `/etc/pokemon-deploy.token` | `root`, dir mode 700 |
| `pokemon/secrets/basicauth.txt` | `/root/pokemon-basicauth.txt` | `root`, dir mode 700 |

`deploy/install_server.sh` rebuilds everything else from the repo: the `pokemon` user, the clone, the venv, both systemd units, the crontab, the Caddy route and the `pokemon-deploy@hetzner` key in root's `authorized_keys`. It is safe to re-run on a live server, which also makes it the repair tool.

After a rebuild:

1. The new server has a new host key: `ssh-keygen -R 65.21.178.63`.
2. If drafter's cloud-init did not run the pokemon installer, root SSH with `~/.ssh/pokemon-hetzner` fails. Reset the root password through the Hetzner API (`actions/reset_password`) and append `~/.ssh/pokemon-hetzner.pub` to `/root/.ssh/authorized_keys` with it.
3. Run the installer: `ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 'bash -s' < deploy/install_server.sh`. It should print `health: ok`.

Hetzner backups are still off for the server. Download a snapshot with `/export-db` (below) before any operation on the server that could destroy data.

Stop the app and checkpoint the WAL (`PRAGMA wal_checkpoint(TRUNCATE)`) before moving or replacing the database file. Streamlit holds it open in WAL mode, so a live `pokemon.db-wal` pairs a stale write-ahead log with whatever file lands under that name next. Replace the file on the volume, not the symlink in `/opt/pokemon`. The restart is required because the app caches its connection with `st.cache_resource`.

> **Gotcha — don't rename `app/views/` back to `app/pages/`.** Streamlit auto-detects any folder literally named `pages/` sibling to the entrypoint as its own multi-page-app router, which registers each page as a standalone top-level route bypassing `main.py`'s custom router (the thing that sets up `st.session_state["conn"]`). Doing so silently breaks every page with a "No database connection." error. The folder is intentionally named `app/views/` for this reason.

---

## Deploying Code Changes

### Deploying via direct SSH (used day-to-day so far)

For any session/machine that already has SSH access (e.g. `~/.ssh/pokemon-hetzner`, outside the office network):

```bash
# 1. Commit and push
git add -A
git commit -m "your message"
git push origin master

# 2. Pull + restart on the server
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 '
  cd /opt/pokemon
  sudo -u pokemon git pull --ff-only
  systemctl restart pokemon-streamlit
  curl -s http://localhost:8502/pokemon/_stcore/health
'
```

### Deploying via the HTTP hook (for use from the office network, where SSH is blocked)

Use the pokemon-scoped deploy hook on port 9001 (mirrors drafter's port-9000 pattern, but requires a bearer token — see `deploy/pokemon_deploy_server.py`):

```bash
# 1. Commit and push
git add -A
git commit -m "your message"
git push origin master

# 2. Pull + restart on server (token stored in /etc/pokemon-deploy.token on the server)
curl -X POST -H "X-Deploy-Token: <token>" http://65.21.178.63:9001/pull
curl -X POST -H "X-Deploy-Token: <token>" http://65.21.178.63:9001/restart

# View recent app logs
curl -X POST -H "X-Deploy-Token: <token>" http://65.21.178.63:9001/logs

# Download a consistent snapshot of the live database
curl -X POST -H "X-Deploy-Token: <token>" http://65.21.178.63:9001/export-db -o pokemon.db
```

---

## First-time setup

`deploy/install_server.sh` does the whole setup; see "What survives a server rebuild" above. It needs drafter's setup first (the mounted volume, Caddy with the `routes.d` import, `python3-venv`, `git`). After it runs, set `DISCORD_WEBHOOK_URL` in `/mnt/drafter-data/pokemon/.env`; cron reads it on the next scrape.

Use `handle` (not `handle_path`) for the Caddy route. `handle_path` strips the `/pokemon` prefix, which breaks Streamlit's `--server.baseUrlPath pokemon` (symptom: basic auth passes, then 404).

The scraper cron belongs to the **`pokemon`** user, not root; `crontab -l` as root shows nothing. Contents (all times UTC):

```
*/20 * * * *  cd /opt/pokemon && venv/bin/python -m scraper >> logs/scraper.log 2>&1
```

---

## Ongoing Operations

| Task | Command |
|------|---------|
| Restart pokemon app | `systemctl restart pokemon-streamlit` |
| View app logs | `journalctl -u pokemon-streamlit -f` |
| View scraper logs | `tail -f /opt/pokemon/logs/scraper.log` |
| Pull latest code (direct SSH) | `ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 'cd /opt/pokemon && sudo -u pokemon git pull --ff-only && systemctl restart pokemon-streamlit'` |
| Pull latest code (HTTP hook, from office network) | `curl -X POST -H "X-Deploy-Token: <token>" http://65.21.178.63:9001/pull` then `.../restart` |
| Run scraper manually | `cd /opt/pokemon && venv/bin/python -m scraper` |
| Reinstall or repair after a server rebuild | `ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 'bash -s' < deploy/install_server.sh` |

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| App not responding | `curl http://localhost:8502/pokemon/_stcore/health` → should be `ok`. The `pokemon` prefix is required: the service runs with `--server.baseUrlPath pokemon`, so the bare path 404s |
| Every page shows "No database connection." | Check the page-source folder is `app/views/`, not `app/pages/` — see the MPA gotcha above |
| Scraper returns 0 products | Check `tail -20 /opt/pokemon/logs/scraper.log`; site may have changed selectors |
| Service not starting | `journalctl -u pokemon-streamlit -n 50` |
| `/pokemon/` serves drafter or 404s | `/etc/caddy/Caddyfile` lost its `import /etc/caddy/routes.d/*.caddy` line (drafter rewrote it); restore it and `systemctl reload caddy` |

---

## Quick Reference

**Deploy code change (direct SSH)**
```bash
git add -A && git commit -m "msg" && git push origin master
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 'cd /opt/pokemon && sudo -u pokemon git pull --ff-only && systemctl restart pokemon-streamlit'
```

**Deploy code change (HTTP hook, from office network)**
```bash
git add -A && git commit -m "msg" && git push origin master
curl -X POST -H "X-Deploy-Token: <token>" http://65.21.178.63:9001/pull
curl -X POST -H "X-Deploy-Token: <token>" http://65.21.178.63:9001/restart
```

**Reinstall or repair the server**
```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 'bash -s' < deploy/install_server.sh
```
