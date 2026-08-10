"""Minimal authenticated HTTP deploy hook for the pokemon app.

Mirrors the sibling drafter project's /opt/upload_server.py pattern (needed
because SSH is blocked from the office network), but requires a bearer
token on every request instead of being open to anyone who knows the IP.

Endpoints (all require header 'X-Deploy-Token: <token>'):
  POST /pull    - git pull --ff-only in /opt/pokemon (run as the pokemon user)
  POST /restart - systemctl restart pokemon-streamlit
  POST /logs    - last 80 lines of the pokemon-streamlit journal
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import hmac
import os
import subprocess

TOKEN = open("/etc/pokemon-deploy.token").read().strip()


class Handler(BaseHTTPRequestHandler):
    def _authorized(self):
        supplied = self.headers.get("X-Deploy-Token", "")
        return hmac.compare_digest(supplied, TOKEN)

    def do_GET(self):
        if self.path.strip("/") == "":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"pokemon deploy hook is running")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if not self._authorized():
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return

        path = self.path.strip("/")
        if path == "pull":
            r = subprocess.run(
                ["sudo", "-u", "pokemon", "git", "-C", "/opt/pokemon", "pull", "--ff-only"],
                capture_output=True, text=True, timeout=30,
            )
            out = r.stdout + r.stderr
            self.send_response(200 if r.returncode == 0 else 500)
            self.end_headers()
            self.wfile.write(out.encode())
        elif path == "restart":
            r = subprocess.run(
                ["systemctl", "restart", "pokemon-streamlit"], capture_output=True, text=True,
            )
            self.send_response(200 if r.returncode == 0 else 500)
            self.end_headers()
            self.wfile.write(b"OK restarted pokemon-streamlit" if r.returncode == 0 else (r.stdout + r.stderr).encode())
        elif path == "logs":
            r = subprocess.run(
                ["journalctl", "-u", "pokemon-streamlit", "--no-pager", "-n", "80"],
                capture_output=True, text=True, timeout=10,
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(r.stdout.encode())
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9001), Handler).serve_forever()
