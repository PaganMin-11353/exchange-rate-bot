#!/usr/bin/env bash
# One-click deploy script for exchange-rate-bot
# Prerequisite: code already cloned, .env already filled with bot token
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="exchange-rate-bot"
SERVICE_FILE="${PROJECT_DIR}/${SERVICE_NAME}.service"
SYSTEMD_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

cd "$PROJECT_DIR"

echo "=== Exchange Rate Bot Deploy ==="

# 1. Check .env
if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run: cp .env.example .env && nano .env"
    exit 1
fi

if grep -q "your_bot_token_here" .env; then
    echo "ERROR: .env still has placeholder token. Fill in TELEGRAM_BOT_TOKEN."
    exit 1
fi

echo "[1/5] .env OK"

# 2. Python venv + deps
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt
echo "[2/5] Dependencies installed"

# 3. Create data dir
mkdir -p data models
echo "[3/5] Directories ready"

# 4. Install systemd service
if [ "$(id -u)" -eq 0 ]; then
    # Update WorkingDirectory and ExecStart to match actual location
    sed "s|/opt/exchange-rate-bot|${PROJECT_DIR}|g" "$SERVICE_FILE" > "$SYSTEMD_PATH"
    # Update User to current SUDO_USER or botuser
    DEPLOY_USER="${SUDO_USER:-$(whoami)}"
    sed -i "s|User=botuser|User=${DEPLOY_USER}|g" "$SYSTEMD_PATH"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    echo "[4/5] systemd service installed (user: ${DEPLOY_USER})"
else
    echo "[4/5] SKIP: not root, run with sudo to install systemd service"
    echo "       Or manually: sudo cp ${SERVICE_FILE} ${SYSTEMD_PATH}"
fi

# 5. Start or restart
if [ "$(id -u)" -eq 0 ]; then
    systemctl restart "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "[5/5] Bot is running"
    else
        echo "[5/5] ERROR: Bot failed to start. Check: sudo journalctl -u ${SERVICE_NAME} -n 30"
        exit 1
    fi
else
    echo "[5/5] SKIP: run 'sudo systemctl start ${SERVICE_NAME}' manually"
fi

echo ""
echo "=== Deploy complete ==="
echo "Commands:"
echo "  scripts/bot.sh status   — check bot status"
echo "  scripts/bot.sh logs     — view live logs"
echo "  scripts/bot.sh update   — pull latest code and restart"
