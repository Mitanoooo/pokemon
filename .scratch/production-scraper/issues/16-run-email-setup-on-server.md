# 16 — Run email setup script on server

## Problem Statement

`scripts/setup_email.py` was built and tested in ticket 14, but has not yet been run on the production server at `/opt/pokemon`. The `.env` file still contains placeholder values for `GMAIL_USER`, `GMAIL_APP_PASSWORD`, and `DIGEST_TO`. Until the script is executed and the credentials validated, `python -m scraper.digest` will raise a `KeyError` and the 05:00 UTC cron job will never send a digest.

## Solution

SSH into the server, run `venv/bin/python scripts/setup_email.py`, follow the prompts, and confirm the test email arrives in the inbox. This is a one-off operator task — no code change is required.

## Steps

1. SSH into the server: `ssh pokemon@65.21.178.63` (or the relevant user)
2. `cd /opt/pokemon`
3. Run: `venv/bin/python scripts/setup_email.py`
4. Enter `GMAIL_USER` (the Gmail sender address)
5. Enter `GMAIL_APP_PASSWORD` (16-char App Password — generate at https://myaccount.google.com/apppasswords; 2FA must be enabled)
6. Enter `DIGEST_TO` (recipient address, or press Enter to use the sender as recipient)
7. Confirm the test email subject `"Pokemon Tracker — test email"` arrives in the inbox
8. Verify `.env` now contains non-placeholder values for all three keys: `grep GMAIL /opt/pokemon/.env`

## Prerequisites

- 2-Factor Authentication enabled on the Google account used as sender
- A Gmail App Password generated at https://myaccount.google.com/apppasswords
- The server is reachable and `/opt/pokemon` is deployed (ticket 09)

## Out of Scope

- Changing the Gmail account or SMTP provider
- Rotating or revoking credentials (re-run the script)

## Further Notes

- The script is idempotent: re-running it overwrites only the three email keys in `.env`; `DB_PATH` and any other keys are preserved.
- If the test email lands in spam, mark it as not-spam — subsequent digest emails will follow the same sender/subject pattern.

**Status:** ready-for-operator

- [ ] SSH into server and run `venv/bin/python scripts/setup_email.py`
- [ ] Test email received in inbox
- [ ] `grep GMAIL /opt/pokemon/.env` shows real credentials (not placeholders)
- [ ] `venv/bin/python -m scraper.digest` runs without `KeyError`
