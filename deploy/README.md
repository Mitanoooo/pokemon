# Deployment Guide — Pokemon Price Tracker

**Server:** Hetzner CX23 at `65.21.178.63`
**OS:** Ubuntu 24.04
**App path:** `/opt/pokemon`
**App port:** 8502 (Streamlit)
**Repo:** `https://github.com/Mitanoooo/pokemon.git`

> **SSH is blocked by corporate firewall.** There is no SSH access from the office network. Deploys from that network go through the pokemon-scoped HTTP deploy hook below — SSH was only ever needed once, from a machine outside the office network, to do the initial bootstrap (already done). Sessions/automation that already have `~/.ssh/pokemon-hetzner` installed (outside the office network) can instead deploy via direct SSH — see "Deploying via direct SSH" below, which is the method actually used day-to-day so far.

> **Shared server.** The drafter app already runs on this server (port 8501, Caddy on port 80). The pokemon app runs on port 8502 and is reachable at `http://65.21.178.63/pokemon/` via a `handle /pokemon/*` block added to the existing Caddyfile, protected by Caddy `basicauth` (username `pokemon`, password given to the project owner out of band — never store it in this repo) — drafter's root route (`reverse_proxy localhost:8501`) is untouched.

**Status: deployed and live** as of 2026-08-10 — app running, systemd service enabled, crontab installed, deploy hook running. Since initial deploy: Backblaze B2/rclone backup was removed entirely (no longer part of this project — SQLite DB is the only copy), a Streamlit multi-page-app bug was fixed (see gotcha below), the first scraper run completed (1,286 readings), and an initial normalisation pass mapped 486 of 1,270 raw names into 146 canonical products (799 remain, to be finished later). Outstanding: Gmail credentials (`scripts/setup_email.py`) still need to be run interactively with real credentials.

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
```

---

## First-Time Setup (Full Deploy) — reference only, already completed

### 1. Clone the repo

```bash
cd /opt/pokemon
git clone https://github.com/Mitanoooo/pokemon.git .
```

### 2. Create the virtualenv and install dependencies

```bash
python3 -m venv /opt/pokemon/venv
/opt/pokemon/venv/bin/pip install --upgrade pip
/opt/pokemon/venv/bin/pip install -r requirements.txt
```

### 3. Create the .env file

```bash
cp /opt/pokemon/.env.example /opt/pokemon/.env
# Edit DB_PATH, then run the email setup script:
/opt/pokemon/venv/bin/python scripts/setup_email.py
```

The email setup script prompts for `GMAIL_USER`, `GMAIL_APP_PASSWORD`, and `DIGEST_TO`, sends a test email, then writes the values to `.env` without touching other keys.

**Gmail App Password prerequisite:** 2-Factor Authentication must be enabled on the Google account. Generate an App Password at <https://myaccount.google.com/apppasswords> — Google shows it with spaces, the script strips them automatically.

### 4. Initialise the database

```bash
cd /opt/pokemon
venv/bin/python init_db.py
```

### 5. Install the systemd service

```bash
cp /opt/pokemon/deploy/pokemon-streamlit.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable pokemon-streamlit
systemctl start pokemon-streamlit
```

Verify it's listening:

```bash
curl -s http://localhost:8502/_stcore/health
# Should return: ok
```

### 6. Configure reverse proxy and basic auth

The app runs on port 8502. Port 80 is already handled by the drafter **Caddy** instance (not nginx) — add a `handle /pokemon/*` block to the existing `/etc/caddy/Caddyfile` (back up the original first), then `systemctl reload caddy` (reload, not restart, so drafter's root route has zero downtime):

```caddyfile
handle /pokemon/* {
    basicauth {
        pokemon <bcrypt-hash>
    }
    reverse_proxy localhost:8502
}
```

Generate the bcrypt hash with `caddy hash-password --plaintext '<password>'`. Do **not** install a second nginx `server {}` block on port 80, and use `handle` (not `handle_path`) — `handle_path` strips the `/pokemon` prefix, which breaks Streamlit's `--server.baseUrlPath pokemon` (symptom: basic auth passes, then 404).

### 7. Add the crontab

```bash
crontab -e
```

Paste from `deploy/crontab.txt` (all times UTC):

```
0 4,16 * * *  cd /opt/pokemon && venv/bin/python -m scraper >> logs/scraper.log 2>&1
0 5 * * *     cd /opt/pokemon && venv/bin/python -m scraper.digest >> logs/digest.log 2>&1
```

### 8. Configure Gmail credentials

```bash
cd /opt/pokemon
venv/bin/python scripts/setup_email.py
```

Skip for now if you don't have credentials yet — the scraper and Streamlit app work without email. The 05:00 UTC digest cron will fail silently until credentials are set.

### 9. Run initial normalisation

After the first scraper run, map raw product names to canonical names:

```bash
cd /opt/pokemon
venv/bin/python -m scraper.normaliser export
venv/bin/python scripts/build_canonical_mappings.py pending_names.json
venv/bin/python -m scraper.normaliser import mappings.json
```

See `docs/normalisation-runbook.md` for the full procedure. Run before the first digest fires.

**Note:** if a mapping is imported for a raw name that was already scraped *before* the mapping existed, `normaliser.py import` also backfills `price_readings.product_id` on those existing rows — no rescrape is needed for the Products page to pick up prices for newly-mapped names.

---

## Ongoing Operations

| Task | Command |
|------|---------|
| Restart pokemon app | `systemctl restart pokemon-streamlit` |
| View app logs | `journalctl -u pokemon-streamlit -f` |
| View scraper logs | `tail -f /opt/pokemon/logs/scraper.log` |
| View digest logs | `tail -f /opt/pokemon/logs/digest.log` |
| Pull latest code (direct SSH) | `ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 'cd /opt/pokemon && sudo -u pokemon git pull --ff-only && systemctl restart pokemon-streamlit'` |
| Pull latest code (HTTP hook, from office network) | `curl -X POST -H "X-Deploy-Token: <token>" http://65.21.178.63:9001/pull` then `.../restart` |
| Run scraper manually | `cd /opt/pokemon && venv/bin/python -m scraper` |
| Run digest manually | `cd /opt/pokemon && venv/bin/python -m scraper.digest` |
| Re-run email setup | `cd /opt/pokemon && venv/bin/python scripts/setup_email.py` |
| Run normalisation (export/map/import) | see step 9 above or `docs/normalisation-runbook.md` |

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| App not responding | `curl http://localhost:8502/_stcore/health` → should be `ok` |
| Every page shows "No database connection." | Check the page-source folder is `app/views/`, not `app/pages/` — see the MPA gotcha above |
| Digest not sending | `grep GMAIL /opt/pokemon/.env` — check credentials are not placeholders |
| `KeyError: GMAIL_APP_PASSWORD` | Run `venv/bin/python scripts/setup_email.py` |
| Scraper returns 0 products | Check `tail -20 /opt/pokemon/logs/scraper.log`; site may have changed selectors |
| Products page empty or missing prices | Run normalisation pass (step 9 above); if names were already mapped but prices still show "—", confirm you're on a version of `normaliser.py` that backfills `price_readings.product_id` (fixed 2026-08-11) |
| Service not starting | `journalctl -u pokemon-streamlit -n 50` |

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

**First-time deploy checklist**
- [ ] Clone repo to `/opt/pokemon`
- [ ] Create venv and install requirements
- [ ] Create `.env` with `DB_PATH`
- [ ] Run `init_db.py`
- [ ] Install and start `pokemon-streamlit` systemd service
- [ ] Add crontab entries
- [ ] Run `scripts/setup_email.py` (can skip initially)
- [ ] Let scraper run once, then run normalisation pass
- [ ] Verify app at `http://localhost:8502/_stcore/health`
