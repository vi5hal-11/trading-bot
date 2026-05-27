#!/bin/bash
# deploy.sh — one-shot bootstrap for a fresh Ubuntu 22.04 / Debian VPS
# Usage: bash deploy.sh https://github.com/YOUR_USERNAME/trading-bot.git
# Run as root or with sudo
set -euo pipefail

REPO_URL="${1:-}"
INSTALL_DIR="/opt/trading-bot"
COMPOSE="docker compose"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║      Trading Bot — VPS Bootstrap         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Install Docker ─────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "▶ Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "✓ Docker installed"
else
    echo "✓ Docker already installed ($(docker --version | cut -d' ' -f3 | tr -d ','))"
fi

# Docker Compose plugin
if ! docker compose version &>/dev/null; then
    echo "▶ Installing docker-compose-plugin..."
    apt-get install -y docker-compose-plugin
fi
echo "✓ Docker Compose $(docker compose version --short)"

# ── 2. Install git ────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    apt-get install -y git
fi

# ── 3. Clone repo ─────────────────────────────────────────────────────────────
if [ -z "$REPO_URL" ]; then
    echo ""
    echo "No repo URL provided."
    echo "Copy your project to $INSTALL_DIR manually, then run:"
    echo "  cd $INSTALL_DIR && nano .env && docker compose up -d"
    exit 0
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "▶ Cloning repo to $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    echo "✓ Cloned"
else
    echo "✓ Repo already present at $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── 4. .env setup ─────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    # Generate a secure JWT secret automatically
    JWT=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    sed -i "s|generate_a_64_char_hex_string_here|$JWT|" .env
    echo ""
    echo "┌─────────────────────────────────────────────────────────┐"
    echo "│  IMPORTANT: Fill in your secrets before starting        │"
    echo "│  nano /opt/trading-bot/.env                             │"
    echo "│                                                         │"
    echo "│  Required:                                              │"
    echo "│    BINANCE_API_KEY        (from Binance API settings)   │"
    echo "│    BINANCE_SECRET_KEY                                   │"
    echo "│    DB_PASSWORD            (choose any strong password)  │"
    echo "│    DASHBOARD_PASSWORD     (web login password)          │"
    echo "│    TELEGRAM_BOT_TOKEN     (from @BotFather)             │"
    echo "│    TELEGRAM_CHAT_ID       (your Telegram user ID)       │"
    echo "│                                                         │"
    echo "│  JWT_SECRET was auto-generated for you ✓                │"
    echo "└─────────────────────────────────────────────────────────┘"
    echo ""
    echo "After editing .env, run:  cd $INSTALL_DIR && bash deploy.sh --start"
    exit 0
fi

# ── 5. --start flag: build and launch ────────────────────────────────────────
if [ "${1:-}" = "--start" ] || [ "${2:-}" = "--start" ]; then
    echo "▶ Building images..."
    $COMPOSE build --parallel
    echo "▶ Starting stack..."
    $COMPOSE up -d
    echo ""
    echo "▶ Waiting for services to be healthy..."
    sleep 10
    $COMPOSE ps
    echo ""
    IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo "╔══════════════════════════════════════════╗"
    echo "║  Bot is running!                         ║"
    echo "║                                          ║"
    echo "║  Dashboard: http://$IP"
    echo "║  Grafana:   http://$IP:3001"
    echo "║  Telegram:  send /help to your bot       ║"
    echo "╚══════════════════════════════════════════╝"
    exit 0
fi

# ── 6. Open firewall ──────────────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    ufw allow 80/tcp   2>/dev/null || true
    ufw allow 3001/tcp 2>/dev/null || true   # Grafana
    ufw allow 22/tcp   2>/dev/null || true   # SSH — keep open!
    echo "✓ Firewall: ports 22, 80, 3001 open"
fi

echo ""
echo "✓ Bootstrap complete. Next steps:"
echo "  1. nano $INSTALL_DIR/.env"
echo "  2. bash $INSTALL_DIR/deploy.sh --start"
