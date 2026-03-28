import pytest
from unittest.mock import patch

from updater import Config, EmailConfig


class TestEmailConfig:
    def test_fields(self):
        email = EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            user="user@example.com",
            password="pass",
            recipient="rcpt@example.com",
        )
        assert email.smtp_host == "smtp.example.com"
        assert email.smtp_port == 587
        assert email.user == "user@example.com"
        assert email.password == "pass"
        assert email.recipient == "rcpt@example.com"


class TestConfig:
    def test_defaults(self):
        cfg = Config(dyfi_user="u", dyfi_pass="p", dyfi_domain="d.dy.fi")
        assert cfg.check_interval == 5
        assert cfg.force_update_days == 2
        assert cfg.log_file == ""
        assert cfg.email is None

    def test_update_url(self):
        cfg = Config(dyfi_user="u", dyfi_pass="p", dyfi_domain="test.dy.fi")
        assert cfg.update_url == "https://www.dy.fi/nic/update?hostname=test.dy.fi"

    def test_force_update_checks(self):
        cfg = Config(
            dyfi_user="u", dyfi_pass="p", dyfi_domain="d.dy.fi",
            check_interval=5, force_update_days=2,
        )
        assert cfg.force_update_checks == 576  # 2*24*60//5

    def test_force_update_checks_custom(self):
        cfg = Config(
            dyfi_user="u", dyfi_pass="p", dyfi_domain="d.dy.fi",
            check_interval=10, force_update_days=1,
        )
        assert cfg.force_update_checks == 144  # 1*24*60//10


class TestConfigFromEnv:
    REQUIRED = {
        "DYFI_USER": "test@example.com",
        "DYFI_PASS": "testpass",
        "DYFI_DOMAIN": "test.dy.fi",
    }

    def test_required_only(self):
        with patch.dict("os.environ", self.REQUIRED, clear=True):
            cfg = Config.from_env()
        assert cfg.dyfi_user == "test@example.com"
        assert cfg.dyfi_pass == "testpass"
        assert cfg.dyfi_domain == "test.dy.fi"
        assert cfg.check_interval == 5
        assert cfg.force_update_days == 2
        assert cfg.log_file == ""
        assert cfg.email is None

    def test_all_optional(self):
        env = {
            **self.REQUIRED,
            "CHECK_INTERVAL_MINUTES": "10",
            "FORCE_UPDATE_DAYS": "3",
            "LOG_FILE": "/tmp/test.log",
        }
        with patch.dict("os.environ", env, clear=True):
            cfg = Config.from_env()
        assert cfg.check_interval == 10
        assert cfg.force_update_days == 3
        assert cfg.log_file == "/tmp/test.log"

    def test_email_enabled(self):
        env = {
            **self.REQUIRED,
            "EMAIL_ENABLED": "true",
            "EMAIL_USER": "sender@gmail.com",
            "EMAIL_PASS": "app_password",
            "EMAIL_RECIPIENT": "rcpt@example.com",
        }
        with patch.dict("os.environ", env, clear=True):
            cfg = Config.from_env()
        assert cfg.email is not None
        assert cfg.email.smtp_host == "smtp.gmail.com"
        assert cfg.email.smtp_port == 587
        assert cfg.email.user == "sender@gmail.com"
        assert cfg.email.password == "app_password"
        assert cfg.email.recipient == "rcpt@example.com"

    def test_email_custom_smtp(self):
        env = {
            **self.REQUIRED,
            "EMAIL_ENABLED": "true",
            "EMAIL_USER": "u",
            "EMAIL_PASS": "p",
            "EMAIL_RECIPIENT": "r",
            "EMAIL_SMTP_HOST": "mail.example.com",
            "EMAIL_SMTP_PORT": "465",
        }
        with patch.dict("os.environ", env, clear=True):
            cfg = Config.from_env()
        assert cfg.email.smtp_host == "mail.example.com"
        assert cfg.email.smtp_port == 465

    def test_email_disabled_by_default(self):
        with patch.dict("os.environ", self.REQUIRED, clear=True):
            cfg = Config.from_env()
        assert cfg.email is None

    def test_missing_dyfi_user(self):
        env = {"DYFI_PASS": "p", "DYFI_DOMAIN": "d"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(KeyError, match="DYFI_USER"):
                Config.from_env()

    def test_missing_dyfi_pass(self):
        env = {"DYFI_USER": "u", "DYFI_DOMAIN": "d"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(KeyError, match="DYFI_PASS"):
                Config.from_env()

    def test_missing_dyfi_domain(self):
        env = {"DYFI_USER": "u", "DYFI_PASS": "p"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(KeyError, match="DYFI_DOMAIN"):
                Config.from_env()

    def test_check_interval_too_low(self):
        env = {**self.REQUIRED, "CHECK_INTERVAL_MINUTES": "0"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="CHECK_INTERVAL_MINUTES must be >= 1"):
                Config.from_env()

    def test_force_update_days_too_low(self):
        env = {**self.REQUIRED, "FORCE_UPDATE_DAYS": "0"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="FORCE_UPDATE_DAYS must be >= 1"):
                Config.from_env()
