#!/bin/bash
# update.sh — pull latest code and restart the stack (zero-downtime where possible)
# Usage: bash update.sh
# Run from /opt/trading-bot or any directory with the repo
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="docker compose"

cd "$INSTALL_DIR"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║      Trading Bot — Update & Restart      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Pull latest code ───────────────────────────────────────────────────────
echo "▶ Pulling latest changes..."
git pull --ff-only
echo "✓ Code updated"

# ── 2. Rebuild images ────────────────────────────────────────────────────────
echo "▶ Rebuilding images..."
$COMPOSE build --parallel
echo "✓ Images rebuilt"

# ── 3. Restart services (keeps postgres + redis running) ─────────────────────
echo "▶ Restarting bot, frontend, nginx..."
$COMPOSE up -d --no-deps bot frontend nginx
echo "✓ Services restarted"

# ── 4. Health check ──────────────────────────────────────────────────────────
echo "▶ Waiting for bot to be ready..."
for i in $(seq 1 15); do
    if curl -sf http://localhost/health >/dev/null 2>&1; then
        echo "✓ Bot healthy"
        break
    fi
    sleep 2
done

echo ""
$COMPOSE ps
echo ""
echo "✓ Update complete — $(date -u '+%Y-%m-%d %H:%M UTC')"
