"""Interactive setup script for Gmail digest credentials.

Usage:
    python scripts/setup_email.py [--env-path /path/to/.env]

Prompts for GMAIL_USER, GMAIL_APP_PASSWORD, DIGEST_TO, then sends a test
email to validate the credentials before writing them to the .env file.
"""
import argparse
import getpass
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path


DEFAULT_ENV_PATH = Path("/opt/pokemon/.env")


def send_test_email(gmail_user: str, app_password: str, digest_to: str) -> bool:
    """Attempt a real STARTTLS connection and send a test message.

    Returns True on success, False on any failure (prints reason).
    """
    msg = MIMEText("This is a test message from the Pokemon Tracker setup script.")
    msg["Subject"] = "Pokemon Tracker — test email"
    msg["From"] = gmail_user
    msg["To"] = digest_to

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_user, app_password)
            server.sendmail(gmail_user, digest_to, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        print(
            "ERROR: Authentication failed. Check that GMAIL_USER is correct and that "
            "GMAIL_APP_PASSWORD is a valid 16-character App Password (not your regular "
            "Google account password). 2FA must be enabled on the account.",
            file=sys.stderr,
        )
        return False
    except smtplib.SMTPException as exc:
        print(f"ERROR: SMTP error — {exc}", file=sys.stderr)
        return False
    except OSError as exc:
        print(f"ERROR: Network error — {exc}", file=sys.stderr)
        return False

    return True


def write_env(env_path: Path, gmail_user: str, app_password: str, digest_to: str) -> None:
    """Write (or update) email keys in the .env file, preserving other keys."""
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            existing[key.strip()] = value.strip()

    existing["GMAIL_USER"] = gmail_user
    existing["GMAIL_APP_PASSWORD"] = app_password
    existing["DIGEST_TO"] = digest_to

    lines = [f"{k}={v}" for k, v in existing.items()]
    env_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Gmail digest credentials.")
    parser.add_argument(
        "--env-path",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=f"Path to .env file (default: {DEFAULT_ENV_PATH})",
    )
    args = parser.parse_args()

    print("Pokemon Tracker — Gmail credential setup")
    print("=" * 42)
    print()

    gmail_user = input("GMAIL_USER (sender address): ").strip()
    if not gmail_user:
        print("ERROR: GMAIL_USER cannot be empty.", file=sys.stderr)
        sys.exit(1)

    app_password = getpass.getpass("GMAIL_APP_PASSWORD (16-char App Password, hidden): ").strip().replace(" ", "")
    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD cannot be empty.", file=sys.stderr)
        sys.exit(1)

    digest_to_input = input(f"DIGEST_TO (recipient, default={gmail_user}): ").strip()
    digest_to = digest_to_input if digest_to_input else gmail_user

    print()
    print(f"Sending test email to {digest_to} …")
    ok = send_test_email(gmail_user, app_password, digest_to)

    if not ok:
        print("Setup aborted — .env not written.", file=sys.stderr)
        sys.exit(1)

    print("Test email sent successfully.")
    write_env(args.env_path, gmail_user, app_password, digest_to)
    print(f".env written to {args.env_path}")
    print()
    print("Done. The cron job will use these credentials at 05:00 UTC.")


if __name__ == "__main__":
    main()
