# Deployment Guide — Pokemon Price Tracker

**Server:** Hetzner CX23 at `65.21.178.63`
**OS:** Ubuntu 24.04
**App path:** `/opt/pokemon`
**App port:** 8502 (Streamlit)
**Repo:** `https://github.com/Mitanoooo/pokemon.git`

> **SSH is blocked by corporate firewall.** There is no SSH access from the office network. Ongoing deploys and management go through the pokemon-scoped HTTP deploy hook below — SSH was only ever needed once, from a machine outside the office network, to do the initial bootstrap (already done).

> **Shared server.** The drafter app already runs on this server (port 8501, Caddy on port 80). The pokemon app runs on port 8502 and is reachable at `http://65.21.178.63/pokemon/` via a `handle /pokemon/*` block added to the existing Caddyfile — drafter's root route (`reverse_proxy localhost:8501`) is untouched.

**Status: deployed and live** as of 2026-08-10 — app running, systemd service enabled, crontab installed, deploy hook running. Outstanding: Gmail credentials (`scripts/setup_email.py`) and Backblaze B2 `rclone config` still need to be run interactively with real credentials.

---

## Deploying Code Changes

For code-only changes (no infrastructure updates), use the pokemon-scoped deploy hook on port 9001 (mirrors drafter's port-9000 pattern, but requires a bearer token — see `deploy/pokemon_deploy_server.py`):

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

### 6. Configure reverse proxy

The app runs on port 8502. Port 80 is already handled by the drafter Caddy instance. Add a path prefix to the existing proxy config, or expose 8502 directly. Do **not** install a second nginx `server {}` block on port 80.

### 7. Create the htpasswd file (if adding basic auth)

```bash
htpasswd -c /etc/nginx/pokemon.htpasswd <username>
```

### 8. Add the crontab

```bash
crontab -e
```

Paste from `deploy/crontab.txt` (all times UTC):

```
0 4,16 * * *  cd /opt/pokemon && venv/bin/python -m scraper >> logs/scraper.log 2>&1
0 5 * * *     cd /opt/pokemon && venv/bin/python -m scraper.digest >> logs/digest.log 2>&1
0 3 * * *     rclone copy /opt/pokemon/pokemon.db b2:pokemon-backup/pokemon.db
```

### 9. Configure rclone for Backblaze B2

```bash
rclone config
```

- Choose `n` (new remote), name it `b2`, type `Backblaze B2`
- Enter your B2 Account ID and Application Key

Verify:

```bash
rclone copy /opt/pokemon/pokemon.db b2:pokemon-backup/pokemon.db
rclone ls b2:pokemon-backup/
```

### 10. Configure Gmail credentials

```bash
cd /opt/pokemon
venv/bin/python scripts/setup_email.py
```

Skip for now if you don't have credentials yet — the scraper and Streamlit app work without email. The 05:00 UTC digest cron will fail silently until credentials are set.

### 11. Run initial normalisation

After the first scraper run, map raw product names to canonical names:

```bash
cd /opt/pokemon
venv/bin/python -m scraper.normaliser export
venv/bin/python scripts/build_canonical_mappings.py pending_names.json
venv/bin/python -m scraper.normaliser import mappings.json
```

See `docs/normalisation-runbook.md` for the full procedure. Run before the first digest fires.

---

## Ongoing Operations

| Task | Command |
|------|---------|
| Restart pokemon app | `systemctl restart pokemon-streamlit` |
| View app logs | `journalctl -u pokemon-streamlit -f` |
| View scraper logs | `tail -f /opt/pokemon/logs/scraper.log` |
| View digest logs | `tail -f /opt/pokemon/logs/digest.log` |
| Pull latest code | `curl -X POST http://65.21.178.63:9000/pull` then `systemctl restart pokemon-streamlit` |
| Run scraper manually | `cd /opt/pokemon && venv/bin/python -m scraper` |
| Run digest manually | `cd /opt/pokemon && venv/bin/python -m scraper.digest` |
| Re-run email setup | `cd /opt/pokemon && venv/bin/python scripts/setup_email.py` |

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| App not responding | `curl http://localhost:8502/_stcore/health` → should be `ok` |
| Digest not sending | `grep GMAIL /opt/pokemon/.env` — check credentials are not placeholders |
| `KeyError: GMAIL_APP_PASSWORD` | Run `venv/bin/python scripts/setup_email.py` |
| Scraper returns 0 products | Check `tail -20 /opt/pokemon/logs/scraper.log`; site may have changed selectors |
| Products page empty | Run normalisation pass (step 11 above) |
| Service not starting | `journalctl -u pokemon-streamlit -n 50` |

---

## Quick Reference

**Deploy code change**
```bash
git add -A && git commit -m "msg" && git push origin main
curl -X POST http://65.21.178.63:9000/pull
systemctl restart pokemon-streamlit
```

**First-time deploy checklist**
- [ ] Clone repo to `/opt/pokemon`
- [ ] Create venv and install requirements
- [ ] Create `.env` with `DB_PATH`
- [ ] Run `init_db.py`
- [ ] Install and start `pokemon-streamlit` systemd service
- [ ] Add crontab entries
- [ ] Configure rclone for B2 backup
- [ ] Run `scripts/setup_email.py` (can skip initially)
- [ ] Let scraper run once, then run normalisation pass
- [ ] Verify app at `http://localhost:8502/_stcore/health`
