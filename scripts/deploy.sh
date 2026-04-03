#!/usr/bin/env bash
# One-click deploy script for exchange-rate-bot
# Usage: sudo scripts/deploy.sh
# Prerequisite: code already cloned, .env already filled with bot token
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="exchange-rate-bot"
SERVICE_FILE="${PROJECT_DIR}/${SERVICE_NAME}.service"
SYSTEMD_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

cd "$PROJECT_DIR"

# Dependency check
for cmd in python3 git; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd not found. Install it first."; exit 1; }
done

# Ensure python3-venv is available
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "python3-venv not found, installing..."
    if [ "$(id -u)" -eq 0 ]; then
        apt-get update -qq && apt-get install -y -qq python3-venv python3-pip
    else
        echo "ERROR: python3-venv is missing. Run: sudo apt install python3-venv python3-pip"
        exit 1
    fi
fi

echo "=== Exchange Rate Bot Deploy ==="

# Determine the actual user (not root when running with sudo)
DEPLOY_USER="${SUDO_USER:-$(whoami)}"

# 1. Check .env
if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run: cp .env.example .env && nano .env"
    exit 1
fi

if grep -q "your_bot_token_here" .env; then
    echo "ERROR: .env still has placeholder token. Fill in TELEGRAM_BOT_TOKEN."
    exit 1
fi

if grep -q "your_api_key_here" .env && ! grep -q "USE_OPEN_API=true" .env; then
    echo "WARNING: EXCHANGERATE_API_KEY has placeholder and USE_OPEN_API is not true."
    echo "         The bot will fail to fetch rates. Set USE_OPEN_API=true or fill in the key."
fi

chmod 600 .env
echo "[1/5] .env OK"

# 2. Python venv + deps (run as deploy user to avoid root-owned files)
if [ ! -d venv ]; then
    sudo -u "$DEPLOY_USER" python3 -m venv venv
fi
sudo -u "$DEPLOY_USER" ./venv/bin/pip install -q -r requirements.txt
echo "[2/5] Dependencies installed"

# 3. Create data dir (owned by deploy user)
mkdir -p data models
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" data models venv .env || {
    echo "WARNING: Could not chown directories to ${DEPLOY_USER}"
}
echo "[3/5] Directories ready"

# 4. Install systemd service
if [ "$(id -u)" -eq 0 ]; then
    # Combine sed substitutions into one command (avoids non-portable sed -i)
    sed -e "s|/opt/exchange-rate-bot|${PROJECT_DIR}|g" \
        -e "s|User=botuser|User=${DEPLOY_USER}|g" \
        "$SERVICE_FILE" > "$SYSTEMD_PATH"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    echo "[4/5] systemd service installed (user: ${DEPLOY_USER})"
else
    echo "[4/5] SKIP: not root, run with sudo to install systemd service"
    echo "       Or manually: sudo cp '${SERVICE_FILE}' '${SYSTEMD_PATH}'"
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
echo "  $0 status   — check bot status"
echo "  $0 logs     — view live logs"
echo "  $0 update   — pull latest code and restart"
