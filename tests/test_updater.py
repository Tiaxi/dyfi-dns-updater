import logging
from logging.handlers import RotatingFileHandler
from unittest.mock import MagicMock, patch

from updater import (
    get_ip_address,
    get_latest_logs,
    handle_signal,
    send_email,
    setup_logging,
    shutdown_event,
    update_dyndns,
)


class TestGetIpAddress:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ip": "1.2.3.4"}
        with patch("updater.requests.get", return_value=mock_resp) as mock_get:
            assert get_ip_address() == "1.2.3.4"
        mock_get.assert_called_once_with(
            "https://api.ipify.org?format=json", timeout=30
        )

    def test_network_error(self):
        with patch("updater.requests.get", side_effect=Exception("timeout")):
            assert get_ip_address() is None


class TestUpdateDyndns:
    def test_good_response(self, config):
        mock_resp = MagicMock(status_code=200, text="good 1.2.3.4")
        with patch("updater.requests.get", return_value=mock_resp):
            assert update_dyndns(config, "1.2.3.4") is True

    def test_nochg_response(self, config):
        mock_resp = MagicMock(status_code=200, text="nochg 1.2.3.4")
        with patch("updater.requests.get", return_value=mock_resp):
            assert update_dyndns(config, "1.2.3.4") is True

    def test_bad_status(self, config):
        mock_resp = MagicMock(status_code=401, text="badauth")
        with patch("updater.requests.get", return_value=mock_resp):
            assert update_dyndns(config, "1.2.3.4") is False

    def test_bad_body(self, config):
        mock_resp = MagicMock(status_code=200, text="abuse")
        with patch("updater.requests.get", return_value=mock_resp):
            assert update_dyndns(config, "1.2.3.4") is False

    def test_network_error(self, config):
        with patch("updater.requests.get", side_effect=Exception("refused")):
            assert update_dyndns(config, "1.2.3.4") is False

    def test_uses_correct_auth(self, config):
        mock_resp = MagicMock(status_code=200, text="good 1.2.3.4")
        with patch("updater.requests.get", return_value=mock_resp) as mock_get:
            update_dyndns(config, "1.2.3.4")
        mock_get.assert_called_once_with(
            config.update_url,
            auth=(config.dyfi_user, config.dyfi_pass),
            timeout=30,
        )


class TestGetLatestLogs:
    def test_disabled(self):
        assert get_latest_logs("") == "(file logging disabled)"

    def test_missing_file(self):
        assert get_latest_logs("/nonexistent/path.log") == "(no log file available)"

    def test_returns_last_10_lines(self, tmp_path):
        log = tmp_path / "test.log"
        lines = [f"line {i}\n" for i in range(20)]
        log.write_text("".join(lines))
        assert get_latest_logs(str(log)) == "".join(lines[-10:])

    def test_fewer_than_10_lines(self, tmp_path):
        log = tmp_path / "short.log"
        log.write_text("line 1\nline 2\n")
        assert get_latest_logs(str(log)) == "line 1\nline 2\n"


class TestSendEmail:
    def _mock_smtp(self, mock_smtp_class):
        """Set up SMTP mock with proper context manager behavior."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        return mock_server

    def test_sends_email(self, config_with_email):
        with patch("updater.smtplib.SMTP") as mock_smtp_class:
            mock_server = self._mock_smtp(mock_smtp_class)
            send_email(config_with_email, "1.2.3.4", success=True)
        mock_smtp_class.assert_called_once_with("smtp.example.com", 587)
        mock_server.ehlo.assert_called_once()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("email@example.com", "emailpass")
        msg = mock_server.send_message.call_args[0][0]
        assert msg["From"] == "email@example.com"
        assert msg["To"] == "recipient@example.com"
        assert "succeeded" in msg["Subject"]
        assert "test.dy.fi" in msg["Subject"]
        assert "1.2.3.4" in msg.get_content()

    def test_failure_subject(self, config_with_email):
        with patch("updater.smtplib.SMTP") as mock_smtp_class:
            mock_server = self._mock_smtp(mock_smtp_class)
            send_email(config_with_email, "1.2.3.4", success=False)
        msg = mock_server.send_message.call_args[0][0]
        assert "FAILED" in msg["Subject"]

    def test_skips_without_config(self, config):
        with patch("updater.smtplib.SMTP") as mock_smtp:
            send_email(config, "1.2.3.4", success=True)
        mock_smtp.assert_not_called()

    def test_smtp_error_caught(self, config_with_email, caplog):
        with patch("updater.smtplib.SMTP") as mock_smtp_class:
            mock_server = self._mock_smtp(mock_smtp_class)
            mock_server.send_message.side_effect = Exception("SMTP error")
            with caplog.at_level(logging.ERROR, logger="dyfi-dns-updater"):
                send_email(config_with_email, "1.2.3.4", success=True)
        assert "Failed to send notification email" in caplog.text


class TestHandleSignal:
    def test_sets_shutdown_event(self):
        assert not shutdown_event.is_set()
        handle_signal(15, None)
        assert shutdown_event.is_set()


class TestSetupLogging:
    def test_console_only(self):
        setup_logging("")
        log = logging.getLogger("dyfi-dns-updater")
        handler_types = [type(h) for h in log.handlers]
        assert logging.StreamHandler in handler_types
        assert RotatingFileHandler not in handler_types
        assert log.level == logging.INFO

    def test_with_file(self, tmp_path):
        setup_logging(str(tmp_path / "test.log"))
        log = logging.getLogger("dyfi-dns-updater")
        handler_types = [type(h) for h in log.handlers]
        assert logging.StreamHandler in handler_types
        assert RotatingFileHandler in handler_types
