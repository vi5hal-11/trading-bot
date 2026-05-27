#!/bin/bash
# deploy.sh — one-shot bootstrap for a fresh Ubuntu/Debian VPS
# Run as root: bash deploy.sh
set -euo pipefail

REPO_URL="${1:-}"  # pass your git repo URL as first arg, or clone manually

echo "=== Trading Bot VPS Bootstrap ==="

# 1. Install Docker + Compose plugin
if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

if ! docker compose version &>/dev/null; then
    echo "Installing docker-compose-plugin..."
    apt-get install -y docker-compose-plugin
fi

# 2. Clone repo (skip if already present)
if [ -n "$REPO_URL" ]; then
    if [ ! -d /opt/trading-bot ]; then
        git clone "$REPO_URL" /opt/trading-bot
    else
        echo "/opt/trading-bot already exists — skipping clone"
    fi
    cd /opt/trading-bot
else
    echo "No repo URL provided. Copy your project to /opt/trading-bot manually, then cd into it."
    exit 0
fi

# 3. Set up .env if not present
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "IMPORTANT: Edit /opt/trading-bot/.env with your credentials before starting."
    echo "  nano /opt/trading-bot/.env"
    echo ""
    echo "Minimum required fields:"
    echo "  BINANCE_API_KEY, BINANCE_SECRET_KEY"
    echo "  DB_PASSWORD, DASHBOARD_PASSWORD, JWT_SECRET"
    echo "  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
    echo ""
    echo "Once edited, run: docker compose up -d"
else
    echo ".env already exists — skipping template copy"
fi

# 4. Open firewall port 80 (ufw)
if command -v ufw &>/dev/null; then
    ufw allow 80/tcp
    ufw allow 3001/tcp  # Grafana (optional)
    echo "ufw: ports 80 and 3001 opened"
fi

echo ""
echo "=== Bootstrap complete ==="
echo "Next steps:"
echo "  1. cd /opt/trading-bot"
echo "  2. nano .env   (fill in your keys)"
echo "  3. docker compose build"
echo "  4. docker compose up -d"
echo "  5. docker compose logs -f bot   (watch startup)"
echo "  6. Visit http://<your-vps-ip>  (dashboard)"
