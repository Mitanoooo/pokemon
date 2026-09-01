# Deployment Guide — Pokemon Price Tracker

**Server:** Hetzner CX23 at `65.21.178.63`
**OS:** Ubuntu 24.04
**App path:** `/opt/pokemon`
**App port:** 8502 (Streamlit)
**Repo:** `https://github.com/Mitanoooo/pokemon.git`

## GitHub authentication (git push from this machine)

The repo remote uses HTTPS. A credential helper reads `$GITHUB_TOKEN` so `git push` works without a password prompt.

**One-time setup (already done on the EC2 dev machine):**

```bash
# 1. Create the credential helper
cat > ~/.git-credential-github << 'EOF'
#!/bin/bash
echo "username=Mitanoooo"
echo "password=$GITHUB_TOKEN"
EOF
chmod +x ~/.git-credential-github

# 2. Tell git to use it for github.com
git config --global credential.https://github.com.helper ~/.git-credential-github

# 3. Add your PAT to ~/.bashrc (replace the placeholder with the real token)
echo 'export GITHUB_TOKEN=your_pat_here' >> ~/.bashrc
```

Then open a new shell (or `source ~/.bashrc`) and `git push` will work.

**If you need to rotate the token:** edit `~/.bashrc`, update `GITHUB_TOKEN`, and `source ~/.bashrc`.

**Required PAT scopes:** `repo` (full control of private repositories).

---

> **SSH is blocked by corporate firewall.** There is no SSH access from the office network. Deploys from that network go through the pokemon-scoped HTTP deploy hook below — SSH was only ever needed once, from a machine outside the office network, to do the initial bootstrap (already done). Sessions/automation that already have `~/.ssh/pokemon-hetzner` installed (outside the office network) can instead deploy via direct SSH — see "Deploying via direct SSH" below, which is the method actually used day-to-day so far.

> **Shared server.** The drafter app already runs on this server (port 8501, Caddy on port 80). The pokemon app runs on port 8502 and is reachable at `http://65.21.178.63/pokemon/` via a `handle /pokemon/*` block added to the existing Caddyfile, protected by Caddy `basicauth` (username `pokemon`, password given to the project owner out of band — never store it in this repo) — drafter's root route (`reverse_proxy localhost:8501`) is untouched.

**Status: deployed and live** as of 2026-08-10. The database is the four tables of the tracker refocus: `sites`, `scrape_runs`, `listings`, `updates`. Mapping, the Cardmarket catalogue, thresholds, price history and the email digest are gone.

**Moving the live database to the four-table schema:** `scripts/rebuild_db.py --source pokemon.db --target pokemon.db.new` builds a new database from the old one and prints per-table source and target counts. `init_db.py` cannot do this: it only creates missing tables and indexes, and refuses a database that predates the refocus. Run the rebuild mid-hour (cron scrapes at :00), check the counts, then swap:

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 '
  cd /opt/pokemon &&
  sudo -u pokemon git pull --ff-only &&
  venv/bin/python scripts/rebuild_db.py --source pokemon.db --target pokemon.db.new &&
  mv pokemon.db pokemon.db.pre-refocus-$(date +%F) &&
  mv pokemon.db.new pokemon.db &&
  chown pokemon:pokemon pokemon.db &&
  systemctl restart pokemon-streamlit
'
```

The `&&` chaining matters: without it a failed rebuild still renames the live database away and swaps in a partial file. The `chown` matters too — the rebuild runs as root, and the app and scraper run as `pokemon`, so a root-owned `pokemon.db` leaves them unable to write.

The restart is required — the app caches its connection with `st.cache_resource`. The archived `pokemon.db.pre-refocus-*` file is where the old price readings live from then on; nothing reads them.

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
# Edit DB_PATH.
```

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

The scraper cron belongs to the **`pokemon`** user, not root. `crontab -l` as root shows nothing.

```bash
crontab -e -u pokemon
# or install the repo file verbatim:
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 'crontab -u pokemon -' < deploy/crontab.txt
```

Contents (all times UTC):

```
0 2-17 * * *  cd /opt/pokemon && venv/bin/python -m scraper >> logs/scraper.log 2>&1
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
| Rebuild the DB from an older schema | `cd /opt/pokemon && venv/bin/python scripts/rebuild_db.py --source pokemon.db --target pokemon.db.new` |

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| App not responding | `curl http://localhost:8502/_stcore/health` → should be `ok` |
| Every page shows "No database connection." | Check the page-source folder is `app/views/`, not `app/pages/` — see the MPA gotcha above |
| Scraper returns 0 products | Check `tail -20 /opt/pokemon/logs/scraper.log`; site may have changed selectors |
| App errors on a missing column | The database predates the four-table schema — run `scripts/rebuild_db.py` and swap the file |
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
- [ ] Verify app at `http://localhost:8502/_stcore/health`
