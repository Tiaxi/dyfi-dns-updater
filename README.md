# dyfi-dns-updater

A lightweight Dynamic DNS updater for [dy.fi](https://www.dy.fi/) — a free Finnish dynamic DNS service.

Monitors your public IP address and automatically updates your dy.fi hostname when it changes. Designed to run continuously on a Raspberry Pi or any Docker-capable host.

## Features

- Polls public IP every 5 minutes (configurable)
- Automatically updates dy.fi when IP changes
- Forces periodic update even without IP change (default: every 2 days)
- Optional email notifications on successful updates
- Graceful shutdown on SIGTERM/SIGINT
- Docker with multi-arch support (amd64, arm64, arm/v7)

## Quick Start (Docker)

1. Clone and configure:

   ```bash
   git clone https://github.com/Tiaxi/dyfi-dns-updater.git
   cd dyfi-dns-updater
   cp .env.example .env
   ```

   Edit `.env` with your dy.fi credentials.

2. Start:

   ```bash
   docker compose up -d
   ```

3. View logs:

   ```bash
   docker compose logs -f
   ```

## Quick Start (Without Docker)

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
export DYFI_USER=your@email.com
export DYFI_PASS=your_password
export DYFI_DOMAIN=yourdomain.dy.fi
uv run updater.py
```

## One-Shot Update

Force a single DNS update and exit:

```bash
docker compose run --rm dyfi-dns-updater --force
```

Or without Docker:

```bash
uv run updater.py --force
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DYFI_USER` | Yes | — | dy.fi account email |
| `DYFI_PASS` | Yes | — | dy.fi password |
| `DYFI_DOMAIN` | Yes | — | Hostname to update (e.g. `example.dy.fi`) |
| `CHECK_INTERVAL_MINUTES` | No | `5` | IP check interval in minutes |
| `FORCE_UPDATE_DAYS` | No | `2` | Force update interval in days |
| `LOG_FILE` | No | *(none)* | Log file path (stdout-only if unset) |
| `EMAIL_ENABLED` | No | `false` | Enable email notifications |
| `EMAIL_USER` | No | — | SMTP login (full email address) |
| `EMAIL_PASS` | No | — | SMTP password (Gmail: use [App Password](https://myaccount.google.com/apppasswords)) |
| `EMAIL_RECIPIENT` | No | — | Notification recipient email |
| `EMAIL_SMTP_HOST` | No | `smtp.gmail.com` | SMTP server hostname |
| `EMAIL_SMTP_PORT` | No | `587` | SMTP server port |

## Multiple Domains

Run separate containers with different environment files:

```bash
cp .env.example .env.domain1  # edit with first domain's credentials
cp .env.example .env.domain2  # edit with second domain's credentials
ENV_FILE=.env.domain1 docker compose -p domain1 up -d
ENV_FILE=.env.domain2 docker compose -p domain2 up -d
```

## Testing

```bash
uv sync   # install dependencies including dev tools
uv run pytest
```

## License

[MIT](LICENSE)
