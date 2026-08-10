# Deployment Guide — Pokemon Price Tracker

Target server: Hetzner CX23 at 65.21.178.63
OS: Ubuntu 22.04 LTS

## Prerequisites

```
apt update && apt install -y python3-venv nginx apache2-utils rclone
```

## 1. Create the app directory and user

```bash
useradd --system --no-create-home --shell /usr/sbin/nologin pokemon
mkdir -p /opt/pokemon
chown pokemon:pokemon /opt/pokemon
```

## 2. Clone the repo

```bash
cd /opt/pokemon
git clone <repo-url> .
chown -R pokemon:pokemon /opt/pokemon
```

## 3. Create the virtualenv and install dependencies

```bash
python3 -m venv /opt/pokemon/venv
/opt/pokemon/venv/bin/pip install --upgrade pip
/opt/pokemon/venv/bin/pip install -r requirements.txt
```

## 4. Create the .env file

```bash
cp /opt/pokemon/.env.example /opt/pokemon/.env
nano /opt/pokemon/.env
```

Fill in `DB_PATH` manually, then run the interactive setup script to configure and validate the Gmail credentials:

```bash
cd /opt/pokemon
venv/bin/python scripts/setup_email.py
```

The script prompts for `GMAIL_USER`, `GMAIL_APP_PASSWORD`, and `DIGEST_TO`, sends a test email to verify the credentials, then writes the values to `/opt/pokemon/.env` without touching other keys like `DB_PATH`.

**Gmail App Password prerequisite:** 2-Factor Authentication must be enabled on the Google account. Generate an App Password at <https://myaccount.google.com/apppasswords>. Google displays it with spaces — the script strips them automatically.

## 5. Initialise the database

```bash
cd /opt/pokemon
venv/bin/python init_db.py
chown pokemon:pokemon pokemon.db
```

## 6. Install the systemd service

```bash
cp /opt/pokemon/deploy/pokemon-streamlit.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable pokemon-streamlit
systemctl start pokemon-streamlit
systemctl status pokemon-streamlit
```

Verify the app is listening: `curl -s http://localhost:8502 | head -5`

## 7. Create the htpasswd file

```bash
htpasswd -c /etc/nginx/pokemon.htpasswd <username>
# Enter and confirm the password when prompted
```

## 8. Configure nginx

```bash
cp /opt/pokemon/deploy/nginx-pokemon.conf /etc/nginx/sites-available/pokemon
ln -s /etc/nginx/sites-available/pokemon /etc/nginx/sites-enabled/pokemon
nginx -t
systemctl reload nginx
```

> **Note:** If a Streamlit app already runs on port 8501 under the default server block,
> move the `location /` block from `nginx-pokemon.conf` into that block rather than
> adding a second `server {}` block on port 80.

## 9. Add the crontab

```bash
crontab -e
```

Paste the contents of `deploy/crontab.txt` (all times are UTC):

```
0 4,16 * * *  cd /opt/pokemon && venv/bin/python -m scraper >> logs/scraper.log 2>&1
0 5 * * *     cd /opt/pokemon && venv/bin/python -m scraper.digest >> logs/digest.log 2>&1
0 3 * * *     rclone copy /opt/pokemon/pokemon.db b2:pokemon-backup/pokemon.db
```

## 10. Configure rclone for Backblaze B2

```bash
rclone config
```

- Choose `n` (new remote)
- Name: `b2`
- Type: `Backblaze B2` (option 5 or search for "b2")
- Enter your B2 Account ID (Application Key ID) and Application Key
- Leave all other settings as defaults

Verify the backup works:

```bash
rclone copy /opt/pokemon/pokemon.db b2:pokemon-backup/pokemon.db
rclone ls b2:pokemon-backup/
```

## Ongoing operations

| Task | Command |
|------|---------|
| View Streamlit logs | `journalctl -u pokemon-streamlit -f` |
| View scraper logs | `tail -f /opt/pokemon/logs/scraper.log` |
| View digest logs | `tail -f /opt/pokemon/logs/digest.log` |
| Restart the app | `systemctl restart pokemon-streamlit` |
| Pull latest code | `cd /opt/pokemon && git pull && systemctl restart pokemon-streamlit` |
| Run scraper manually | `cd /opt/pokemon && venv/bin/python -m scraper` |
| Run digest manually | `cd /opt/pokemon && venv/bin/python -m scraper.digest` |
