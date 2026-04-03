import argparse
import logging
import os
import signal
import smtplib
import ssl
import sys
import threading
from collections import deque
from dataclasses import dataclass
from email.message import EmailMessage
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests

logger = logging.getLogger("dyfi-dns-updater")
shutdown_event = threading.Event()


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int
    user: str
    password: str
    recipient: str


@dataclass
class Config:
    dyfi_user: str
    dyfi_pass: str
    dyfi_domain: str
    check_interval: int = 5
    force_update_days: int = 2
    log_file: str = ""
    email: EmailConfig | None = None

    @property
    def update_url(self) -> str:
        return f"https://www.dy.fi/nic/update?hostname={self.dyfi_domain}"

    @property
    def force_update_checks(self) -> int:
        return self.force_update_days * 24 * 60 // self.check_interval

    @classmethod
    def from_env(cls) -> "Config":
        email = None
        if os.environ.get("EMAIL_ENABLED", "false").lower() == "true":
            email = EmailConfig(
                smtp_host=os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(os.environ.get("EMAIL_SMTP_PORT", "587")),
                user=os.environ["EMAIL_USER"],
                password=os.environ["EMAIL_PASS"],
                recipient=os.environ["EMAIL_RECIPIENT"],
            )
        check_interval = int(os.environ.get("CHECK_INTERVAL_MINUTES", "5"))
        if check_interval < 1:
            raise ValueError(f"CHECK_INTERVAL_MINUTES must be >= 1, got {check_interval}")
        force_update_days = int(os.environ.get("FORCE_UPDATE_DAYS", "2"))
        if force_update_days < 1:
            raise ValueError(f"FORCE_UPDATE_DAYS must be >= 1, got {force_update_days}")
        return cls(
            dyfi_user=os.environ["DYFI_USER"],
            dyfi_pass=os.environ["DYFI_PASS"],
            dyfi_domain=os.environ["DYFI_DOMAIN"],
            check_interval=check_interval,
            force_update_days=force_update_days,
            log_file=os.environ.get("LOG_FILE", ""),
            email=email,
        )


def handle_signal(signum, _frame):
    logger.info(f"Received signal {signum}, shutting down")
    shutdown_event.set()


def setup_logging(log_file: str) -> None:
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s", datefmt="%d.%m.%Y %H:%M:%S"
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, mode="a", maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)


def get_ip_address() -> str | None:
    try:
        return requests.get("https://api.ipify.org?format=json", timeout=30).json()["ip"]
    except Exception:
        logger.warning("Could not get IP address", exc_info=True)
        return None


def update_dyndns(config: Config, ip_address: str) -> bool:
    logger.info(f"Updating dy.fi DNS for {config.dyfi_domain}")
    try:
        r = requests.get(
            config.update_url,
            auth=(config.dyfi_user, config.dyfi_pass),
            timeout=30,
        )
    except Exception:
        logger.error("Could not reach dy.fi", exc_info=True)
        return False
    body = r.text.strip()
    if r.status_code == 200 and body.startswith(("good", "nochg")):
        logger.info(f"Updated successfully to {ip_address} (response: {body})")
        return True
    logger.warning(f"dy.fi update failed: HTTP {r.status_code}, body: {body}")
    return False


def get_latest_logs(log_file: str) -> str:
    if not log_file:
        return "(file logging disabled)"
    try:
        with open(log_file) as f:
            return "".join(deque(f, 10))
    except FileNotFoundError:
        return "(no log file available)"


def send_email(config: Config, ip_address: str, success: bool) -> None:
    if not config.email:
        return
    status = "succeeded" if success else "FAILED"
    subject = f"dy.fi DNS update {status} for {config.dyfi_domain}"
    latest_logs = get_latest_logs(config.log_file)
    body = f"IP address: {ip_address}\nStatus: {status}\n\nRecent logs:\n{latest_logs}"

    msg = EmailMessage()
    msg["From"] = config.email.user
    msg["To"] = config.email.recipient
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(config.email.smtp_host, config.email.smtp_port) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.login(config.email.user, config.email.password)
            server.send_message(msg)
        logger.info(f"Sent notification to {config.email.recipient}")
    except Exception:
        logger.error("Failed to send notification email", exc_info=True)


def run_force_update(config: Config) -> None:
    ip_address = get_ip_address()
    if not ip_address:
        logger.error("Could not determine IP address, aborting")
        sys.exit(1)
    logger.info(f"Current IP address is {ip_address}")
    success = update_dyndns(config, ip_address)
    send_email(config, ip_address, success)
    sys.exit(0 if success else 1)


def run_polling_loop(config: Config) -> None:
    logger.info(f"Check interval: {config.check_interval} minutes")
    logger.info(f"Force update interval: {config.force_update_days} days")
    prev_ip = get_ip_address()
    if prev_ip:
        logger.info(f"Initial IP address is {prev_ip}")
    checks = 0

    while not shutdown_event.is_set():
        ip = get_ip_address()
        if ip:
            logger.info(
                f"Current IP address is {ip}"
                f" (check {checks}/{config.force_update_checks})"
            )
            force = checks >= config.force_update_checks
            if prev_ip != ip or force:
                if force:
                    logger.info(
                        f"Forcing update after {checks} checks "
                        f"({config.force_update_days} days)"
                    )
                else:
                    logger.info(f"IP address changed: {prev_ip} -> {ip}")
                success = update_dyndns(config, ip)
                if success:
                    prev_ip = ip
                    checks = 0
                    send_email(config, ip, success=True)
                else:
                    if force:
                        send_email(config, ip, success=False)
                    logger.error("Update failed, will retry")
        Path("/tmp/healthcheck").touch()
        checks += 1
        if shutdown_event.wait(timeout=config.check_interval * 60):
            break

    logger.info("Shutdown complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="dy.fi Dynamic DNS Updater")
    parser.add_argument("--force", action="store_true", help="Force a single update and exit")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    config = Config.from_env()
    setup_logging(config.log_file)
    logger.info("dyfi-dns-updater started")

    if args.force:
        run_force_update(config)
    else:
        run_polling_loop(config)


if __name__ == "__main__":
    main()
