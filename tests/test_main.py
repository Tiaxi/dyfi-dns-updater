import pytest
from unittest.mock import patch, MagicMock

from updater import Config, main, run_force_update, run_polling_loop, shutdown_event


class TestRunForceUpdate:
    def test_success_exits_0(self, config):
        with (
            patch("updater.get_ip_address", return_value="1.2.3.4"),
            patch("updater.update_dyndns", return_value=True) as mock_update,
            patch("updater.send_email") as mock_email,
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_force_update(config)
        assert exc_info.value.code == 0
        mock_update.assert_called_once_with(config, "1.2.3.4")
        mock_email.assert_called_once_with(config, "1.2.3.4", True)

    def test_failure_exits_1(self, config):
        with (
            patch("updater.get_ip_address", return_value="1.2.3.4"),
            patch("updater.update_dyndns", return_value=False),
            patch("updater.send_email") as mock_email,
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_force_update(config)
        assert exc_info.value.code == 1
        mock_email.assert_called_once_with(config, "1.2.3.4", False)

    def test_no_ip_exits_1(self, config):
        with patch("updater.get_ip_address", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                run_force_update(config)
        assert exc_info.value.code == 1


class TestRunPollingLoop:
    def test_ip_change_triggers_update(self, config):
        with (
            patch("updater.get_ip_address", side_effect=["1.1.1.1", "2.2.2.2"]),
            patch("updater.update_dyndns", return_value=True) as mock_update,
            patch("updater.send_email") as mock_email,
            patch.object(shutdown_event, "is_set", side_effect=[False, True]),
            patch.object(shutdown_event, "wait", return_value=False),
            patch("updater.Path"),
        ):
            run_polling_loop(config)
        mock_update.assert_called_once_with(config, "2.2.2.2")
        mock_email.assert_called_once_with(config, "2.2.2.2", success=True)

    def test_same_ip_no_update(self, config):
        with (
            patch("updater.get_ip_address", return_value="1.1.1.1"),
            patch("updater.update_dyndns") as mock_update,
            patch.object(shutdown_event, "is_set", side_effect=[False, True]),
            patch.object(shutdown_event, "wait", return_value=False),
            patch("updater.Path"),
        ):
            run_polling_loop(config)
        mock_update.assert_not_called()

    def test_force_update_after_interval(self):
        # force_update_checks = 1*24*60//1440 = 1
        cfg = Config(
            dyfi_user="u", dyfi_pass="p", dyfi_domain="d.dy.fi",
            check_interval=1440, force_update_days=1,
        )
        with (
            patch("updater.get_ip_address", return_value="1.1.1.1"),
            patch("updater.update_dyndns", return_value=True) as mock_update,
            patch("updater.send_email"),
            # iter1: checks=0 < 1, skip. iter2: checks=1 >= 1, force. iter3: exit
            patch.object(shutdown_event, "is_set", side_effect=[False, False, True]),
            patch.object(shutdown_event, "wait", return_value=False),
            patch("updater.Path"),
        ):
            run_polling_loop(cfg)
        mock_update.assert_called_once_with(cfg, "1.1.1.1")

    def test_update_failure_retries(self, config):
        with (
            patch("updater.get_ip_address", side_effect=["1.1.1.1", "2.2.2.2", "2.2.2.2"]),
            patch("updater.update_dyndns", side_effect=[False, True]) as mock_update,
            patch("updater.send_email") as mock_email,
            patch.object(shutdown_event, "is_set", side_effect=[False, False, True]),
            patch.object(shutdown_event, "wait", return_value=False),
            patch("updater.Path"),
        ):
            run_polling_loop(config)
        assert mock_update.call_count == 2
        # Email only sent on success (not on IP-change failure)
        mock_email.assert_called_once_with(config, "2.2.2.2", success=True)

    def test_force_update_failure_sends_email(self):
        cfg = Config(
            dyfi_user="u", dyfi_pass="p", dyfi_domain="d.dy.fi",
            check_interval=1440, force_update_days=1,
        )
        with (
            patch("updater.get_ip_address", return_value="1.1.1.1"),
            patch("updater.update_dyndns", return_value=False),
            patch("updater.send_email") as mock_email,
            patch.object(shutdown_event, "is_set", side_effect=[False, False, True]),
            patch.object(shutdown_event, "wait", return_value=False),
            patch("updater.Path"),
        ):
            run_polling_loop(cfg)
        mock_email.assert_called_once_with(cfg, "1.1.1.1", success=False)

    def test_ip_failure_skips_update(self, config):
        with (
            patch("updater.get_ip_address", side_effect=["1.1.1.1", None]),
            patch("updater.update_dyndns") as mock_update,
            patch.object(shutdown_event, "is_set", side_effect=[False, True]),
            patch.object(shutdown_event, "wait", return_value=False),
            patch("updater.Path"),
        ):
            run_polling_loop(config)
        mock_update.assert_not_called()

    def test_initial_ip_failure(self, config):
        with (
            patch("updater.get_ip_address", side_effect=[None, "1.1.1.1"]),
            patch("updater.update_dyndns", return_value=True) as mock_update,
            patch("updater.send_email"),
            patch.object(shutdown_event, "is_set", side_effect=[False, True]),
            patch.object(shutdown_event, "wait", return_value=False),
            patch("updater.Path"),
        ):
            run_polling_loop(config)
        # prev_ip=None != ip="1.1.1.1" triggers update
        mock_update.assert_called_once_with(config, "1.1.1.1")

    def test_shutdown_breaks_loop(self, config):
        with (
            patch("updater.get_ip_address", return_value="1.1.1.1"),
            patch.object(shutdown_event, "is_set", side_effect=[False, True]),
            patch.object(shutdown_event, "wait", return_value=True),
            patch("updater.Path"),
        ):
            run_polling_loop(config)
        # Passes if no infinite loop


class TestMain:
    def test_force_flag(self):
        with (
            patch("sys.argv", ["updater.py", "--force"]),
            patch("updater.Config.from_env") as mock_env,
            patch("updater.setup_logging"),
            patch("updater.run_force_update") as mock_force,
        ):
            mock_env.return_value = Config(
                dyfi_user="u", dyfi_pass="p", dyfi_domain="d.dy.fi"
            )
            main()
        mock_force.assert_called_once()

    def test_polling_mode(self):
        with (
            patch("sys.argv", ["updater.py"]),
            patch("updater.Config.from_env") as mock_env,
            patch("updater.setup_logging"),
            patch("updater.run_polling_loop") as mock_poll,
        ):
            mock_env.return_value = Config(
                dyfi_user="u", dyfi_pass="p", dyfi_domain="d.dy.fi"
            )
            main()
        mock_poll.assert_called_once()

    def test_setup_logging_called(self):
        with (
            patch("sys.argv", ["updater.py"]),
            patch("updater.Config.from_env") as mock_env,
            patch("updater.setup_logging") as mock_setup,
            patch("updater.run_polling_loop"),
        ):
            mock_env.return_value = Config(
                dyfi_user="u", dyfi_pass="p", dyfi_domain="d.dy.fi",
                log_file="/tmp/test.log",
            )
            main()
        mock_setup.assert_called_once_with("/tmp/test.log")
