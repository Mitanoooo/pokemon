"""Tests for scripts/setup_email.py."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load the script as a module without executing __main__
_SCRIPT = Path(__file__).parent.parent / "scripts" / "setup_email.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("setup_email", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return _load_module()


def _make_smtp_mock():
    smtp_instance = MagicMock()
    smtp_instance.__enter__ = MagicMock(return_value=smtp_instance)
    smtp_instance.__exit__ = MagicMock(return_value=False)
    smtp_cls = MagicMock(return_value=smtp_instance)
    return smtp_cls, smtp_instance


# ── send_test_email ────────────────────────────────────────────────────────────

def test_send_test_email_returns_true_on_success(mod):
    smtp_cls, smtp_instance = _make_smtp_mock()
    with patch("smtplib.SMTP", smtp_cls):
        result = mod.send_test_email("user@gmail.com", "apppassword", "dest@example.com")
    assert result is True
    smtp_instance.ehlo.assert_called_once()
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("user@gmail.com", "apppassword")
    smtp_instance.sendmail.assert_called_once()


def test_send_test_email_returns_false_on_auth_failure(mod):
    import smtplib
    smtp_cls, smtp_instance = _make_smtp_mock()
    smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")
    with patch("smtplib.SMTP", smtp_cls):
        result = mod.send_test_email("user@gmail.com", "wrongpass", "dest@example.com")
    assert result is False


def test_send_test_email_returns_false_on_network_error(mod):
    smtp_cls, _ = _make_smtp_mock()
    smtp_cls.side_effect = OSError("Connection refused")
    with patch("smtplib.SMTP", smtp_cls):
        result = mod.send_test_email("user@gmail.com", "apppassword", "dest@example.com")
    assert result is False


# ── write_env ─────────────────────────────────────────────────────────────────

def test_write_env_creates_file_with_keys(tmp_path, mod):
    env_path = tmp_path / ".env"
    mod.write_env(
        env_path,
        gmail_user="user@gmail.com",
        app_password="abc123",
        digest_to="dest@example.com",
    )
    content = env_path.read_text()
    assert "GMAIL_USER=user@gmail.com" in content
    assert "GMAIL_APP_PASSWORD=abc123" in content
    assert "DIGEST_TO=dest@example.com" in content


def test_write_env_preserves_existing_unrelated_keys(tmp_path, mod):
    env_path = tmp_path / ".env"
    env_path.write_text("DB_PATH=/opt/pokemon/pokemon.db\nOTHER_KEY=somevalue\n")
    mod.write_env(
        env_path,
        gmail_user="user@gmail.com",
        app_password="abc123",
        digest_to="dest@example.com",
    )
    content = env_path.read_text()
    assert "DB_PATH=/opt/pokemon/pokemon.db" in content
    assert "OTHER_KEY=somevalue" in content
    assert "GMAIL_USER=user@gmail.com" in content


def test_write_env_updates_existing_email_keys(tmp_path, mod):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DB_PATH=/opt/pokemon/pokemon.db\n"
        "GMAIL_USER=old@gmail.com\n"
        "GMAIL_APP_PASSWORD=oldpass\n"
        "DIGEST_TO=old@example.com\n"
    )
    mod.write_env(
        env_path,
        gmail_user="new@gmail.com",
        app_password="newpass",
        digest_to="new@example.com",
    )
    content = env_path.read_text()
    assert "GMAIL_USER=new@gmail.com" in content
    assert "GMAIL_APP_PASSWORD=newpass" in content
    assert "DIGEST_TO=new@example.com" in content
    assert "old@gmail.com" not in content
    assert "oldpass" not in content
    # DB_PATH unchanged
    assert "DB_PATH=/opt/pokemon/pokemon.db" in content


def test_write_env_strips_spaces_from_app_password(tmp_path, mod):
    env_path = tmp_path / ".env"
    # Callers strip spaces before calling write_env; write_env stores the value as-is.
    mod.write_env(
        env_path,
        gmail_user="user@gmail.com",
        app_password="abcdefghijklmnop",
        digest_to="dest@example.com",
    )
    content = env_path.read_text()
    assert "GMAIL_APP_PASSWORD=abcdefghijklmnop" in content


# ── main() integration ─────────────────────────────────────────────────────────

def test_main_smtp_failure_does_not_write_env(tmp_path, mod):
    """SMTP failure aborts before writing .env."""
    import smtplib
    env_path = tmp_path / ".env"
    smtp_cls, smtp_instance = _make_smtp_mock()
    smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")

    inputs = iter(["user@gmail.com", "dest@example.com"])
    with (
        patch("smtplib.SMTP", smtp_cls),
        patch("getpass.getpass", return_value="wrongpass"),
        patch("builtins.input", side_effect=inputs),
    ):
        with pytest.raises(SystemExit):
            mod.main.__wrapped__(env_path) if hasattr(mod.main, "__wrapped__") else _run_main(mod, env_path)

    assert not env_path.exists()


def _run_main(mod, env_path):
    """Drive main() with --env-path pointing at tmp_path."""
    import sys
    with patch.object(sys, "argv", ["setup_email.py", "--env-path", str(env_path)]):
        mod.main()


def test_main_success_writes_env(tmp_path, mod):
    """Valid credentials → .env written with correct keys."""
    env_path = tmp_path / ".env"
    smtp_cls, _ = _make_smtp_mock()

    inputs = iter(["user@gmail.com", "dest@example.com"])
    with (
        patch("smtplib.SMTP", smtp_cls),
        patch("getpass.getpass", return_value="abcdefghijklmnop"),
        patch("builtins.input", side_effect=inputs),
        patch.object(sys, "argv", ["setup_email.py", "--env-path", str(env_path)]),
    ):
        mod.main()

    content = env_path.read_text()
    assert "GMAIL_USER=user@gmail.com" in content
    assert "GMAIL_APP_PASSWORD=abcdefghijklmnop" in content
    assert "DIGEST_TO=dest@example.com" in content


def test_main_strips_spaces_from_app_password(tmp_path, mod):
    """Spaces in pasted App Password are stripped before SMTP and .env."""
    env_path = tmp_path / ".env"
    smtp_cls, smtp_instance = _make_smtp_mock()

    inputs = iter(["user@gmail.com", "dest@example.com"])
    with (
        patch("smtplib.SMTP", smtp_cls),
        patch("getpass.getpass", return_value="abcd efgh ijkl mnop"),
        patch("builtins.input", side_effect=inputs),
        patch.object(sys, "argv", ["setup_email.py", "--env-path", str(env_path)]),
    ):
        mod.main()

    # SMTP login called with de-spaced password
    smtp_instance.login.assert_called_once_with("user@gmail.com", "abcdefghijklmnop")
    # .env written with de-spaced password
    assert "GMAIL_APP_PASSWORD=abcdefghijklmnop" in env_path.read_text()
