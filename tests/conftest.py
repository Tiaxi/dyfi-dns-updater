import logging

import pytest

from updater import Config, EmailConfig, shutdown_event


@pytest.fixture
def config():
    return Config(
        dyfi_user="test@example.com",
        dyfi_pass="testpass",
        dyfi_domain="test.dy.fi",
    )


@pytest.fixture
def config_with_email():
    return Config(
        dyfi_user="test@example.com",
        dyfi_pass="testpass",
        dyfi_domain="test.dy.fi",
        email=EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            user="email@example.com",
            password="emailpass",
            recipient="recipient@example.com",
        ),
    )


@pytest.fixture(autouse=True)
def _clear_shutdown():
    shutdown_event.clear()
    yield
    shutdown_event.clear()


@pytest.fixture(autouse=True)
def _clean_logger():
    log = logging.getLogger("dyfi-dns-updater")
    original_handlers = log.handlers.copy()
    original_level = log.level
    yield
    for h in log.handlers:
        if h not in original_handlers:
            h.close()
    log.handlers = original_handlers
    log.level = original_level
