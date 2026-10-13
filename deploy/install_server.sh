#!/usr/bin/env bash
# Install or repair the pokemon app on the shared Hetzner server. Run as root; safe to re-run.
# Drafter's cloud-init runs this at the end of every rebuild. Everything that must outlive a
# rebuild (database, .env, deploy token, basicauth password) lives on the drafter-data volume.
set -euo pipefail

APP=/opt/pokemon
DATA=/mnt/drafter-data/pokemon
SECRETS=$DATA/secrets
DEPLOY_KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ5so1nwp1E1duDoGfZADuRGaWcVH2M5WExm63OA3iRd pokemon-deploy@hetzner'

mountpoint -q /mnt/drafter-data || { echo "drafter-data volume is not mounted" >&2; exit 1; }

umask 022
mkdir -p /root/.ssh
chmod 700 /root/.ssh
grep -qF "$DEPLOY_KEY" /root/.ssh/authorized_keys 2>/dev/null || echo "$DEPLOY_KEY" >> /root/.ssh/authorized_keys

id pokemon >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin pokemon

mkdir -p "$DATA" "$SECRETS"
chown pokemon:pokemon "$DATA"
chmod 700 "$SECRETS"

if [ ! -d "$APP/.git" ]; then
  mkdir -p "$APP"
  chown pokemon:pokemon "$APP"
  sudo -u pokemon git clone https://github.com/Mitanoooo/pokemon.git "$APP"
fi
cd "$APP"
sudo -u pokemon mkdir -p logs

[ -e pokemon.db ] || sudo -u pokemon ln -s "$DATA/pokemon.db" pokemon.db

# A regular file here predates the volume layout; move it onto the volume.
[ -f .env ] && [ ! -L .env ] && [ ! -e "$DATA/.env" ] && mv .env "$DATA/.env"
if [ ! -e "$DATA/.env" ]; then
  printf 'DB_PATH=%s/pokemon.db\nDISCORD_WEBHOOK_URL=\n' "$APP" > "$DATA/.env"
fi
chown pokemon:pokemon "$DATA/.env"
chmod 600 "$DATA/.env"
ln -sfn "$DATA/.env" .env

[ -x venv/bin/python ] || sudo -u pokemon python3 -m venv venv
sudo -u pokemon venv/bin/pip install -q --upgrade pip
sudo -u pokemon venv/bin/pip install -q -r requirements.txt

sudo -u pokemon venv/bin/python init_db.py pokemon.db

[ -f /etc/pokemon-deploy.token ] && [ ! -L /etc/pokemon-deploy.token ] && [ ! -e "$SECRETS/deploy.token" ] \
  && mv /etc/pokemon-deploy.token "$SECRETS/deploy.token"
[ -e "$SECRETS/deploy.token" ] || (umask 077; openssl rand -hex 32 > "$SECRETS/deploy.token")
ln -sfn "$SECRETS/deploy.token" /etc/pokemon-deploy.token

[ -f /root/pokemon-basicauth.txt ] && [ ! -L /root/pokemon-basicauth.txt ] && [ ! -e "$SECRETS/basicauth.txt" ] \
  && mv /root/pokemon-basicauth.txt "$SECRETS/basicauth.txt"
[ -e "$SECRETS/basicauth.txt" ] || (umask 077; openssl rand -base64 18 | tr -d '/+=' > "$SECRETS/basicauth.txt")
ln -sfn "$SECRETS/basicauth.txt" /root/pokemon-basicauth.txt

cp deploy/pokemon-streamlit.service deploy/pokemon-deploy.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable pokemon-streamlit pokemon-deploy
systemctl restart pokemon-streamlit pokemon-deploy

crontab -u pokemon deploy/crontab.txt

# Drafter's Caddyfile imports /etc/caddy/routes.d/*.caddy ahead of its catch-all route.
hash=$(caddy hash-password --plaintext "$(cat "$SECRETS/basicauth.txt")")
mkdir -p /etc/caddy/routes.d
cat > /etc/caddy/routes.d/pokemon.caddy <<EOF
redir /pokemon /pokemon/
handle /pokemon/* {
	basicauth {
		pokemon $hash
	}
	reverse_proxy localhost:8502
}
EOF
caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile >/dev/null
systemctl reload caddy

sleep 5
echo "health: $(curl -s http://localhost:8502/pokemon/_stcore/health)"
grep -q 'routes.d' /etc/caddy/Caddyfile || echo "WARNING: /etc/caddy/Caddyfile does not import routes.d; /pokemon/ is not routed" >&2
