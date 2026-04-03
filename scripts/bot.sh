#!/usr/bin/env bash
# Management script for exchange-rate-bot
set -euo pipefail

SERVICE="exchange-rate-bot"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB="${PROJECT_DIR}/data/bot.db"

usage() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  status    — service status and memory usage"
    echo "  logs      — live log stream (Ctrl+C to exit)"
    echo "  log       — last 50 lines of log file"
    echo "  update    — git pull, pip install, restart"
    echo "  restart   — restart the bot"
    echo "  stop      — stop the bot"
    echo "  start     — start the bot"
    echo "  api       — show monthly API call count"
    echo "  users     — show registered users"
    echo "  reset-user <id> — delete a user and their settings"
    echo "  db        — open sqlite3 shell"
    echo "  help      — show this message"
}

case "${1:-}" in
    status)
        echo "=== Service ==="
        systemctl status "$SERVICE" --no-pager 2>/dev/null || echo "Service not installed"
        echo ""
        echo "=== Memory ==="
        ps aux | head -1
        ps aux | grep "[b]ot.main" || echo "Bot process not found"
        echo ""
        echo "=== DB Size ==="
        ls -lh "$DB" 2>/dev/null || echo "No database yet"
        ;;

    logs)
        journalctl -u "$SERVICE" -f 2>/dev/null || sudo journalctl -u "$SERVICE" -f
        ;;

    log)
        if [ -f "${PROJECT_DIR}/data/bot.log" ]; then
            tail -50 "${PROJECT_DIR}/data/bot.log"
        else
            echo "No log file yet. Try: $0 logs"
        fi
        ;;

    update)
        echo "=== Pulling latest code ==="
        cd "$PROJECT_DIR"
        if ! git diff --quiet HEAD 2>/dev/null; then
            echo "WARNING: Local changes detected. Stash or commit before updating."
            exit 1
        fi
        git pull
        echo ""
        echo "=== Installing dependencies ==="
        if [ ! -f venv/bin/pip ]; then
            echo "ERROR: venv not found. Run deploy.sh first."
            exit 1
        fi
        if ! venv/bin/python -c "import sys" 2>/dev/null; then
            echo "WARNING: venv appears broken, recreating..."
            rm -rf venv
            python3 -m venv venv
        fi
        venv/bin/pip install -q -r requirements.txt
        echo ""
        echo "=== Restarting ==="
        sudo systemctl restart "$SERVICE"
        sleep 2
        systemctl status "$SERVICE" --no-pager
        ;;

    restart)
        sudo systemctl restart "$SERVICE"
        sleep 2
        systemctl status "$SERVICE" --no-pager
        ;;

    stop)
        sudo systemctl stop "$SERVICE"
        echo "Bot stopped"
        ;;

    start)
        sudo systemctl start "$SERVICE"
        sleep 2
        systemctl status "$SERVICE" --no-pager
        ;;

    api)
        command -v sqlite3 >/dev/null 2>&1 || { echo "ERROR: sqlite3 not found."; exit 1; }
        if [ -f "$DB" ]; then
            echo "=== Monthly API Usage ==="
            sqlite3 "$DB" "SELECT month, call_count FROM api_usage ORDER BY month DESC LIMIT 6;"
        else
            echo "No database yet"
        fi
        ;;

    users)
        command -v sqlite3 >/dev/null 2>&1 || { echo "ERROR: sqlite3 not found."; exit 1; }
        if [ -f "$DB" ]; then
            echo "=== Registered Users ==="
            sqlite3 "$DB" -header -column \
                "SELECT u.user_id, u.username, u.home_currency, u.interval_hours, u.is_active,
                        GROUP_CONCAT(ut.target_currency) as targets
                 FROM users u
                 LEFT JOIN user_targets ut ON u.user_id = ut.user_id
                 GROUP BY u.user_id;"
        else
            echo "No database yet"
        fi
        ;;

    reset-user)
        command -v sqlite3 >/dev/null 2>&1 || { echo "ERROR: sqlite3 not found."; exit 1; }
        if [ -z "${2:-}" ]; then
            echo "Usage: $0 reset-user <user_id>"
            echo ""
            echo "Current users:"
            sqlite3 "$DB" -header -column "SELECT user_id, username FROM users;" 2>/dev/null || echo "No database yet"
            exit 1
        fi
        if [ -f "$DB" ]; then
            sqlite3 "$DB" "DELETE FROM user_targets WHERE user_id = $2; DELETE FROM users WHERE user_id = $2;"
            echo "User $2 deleted. They can re-run /start as a new user."
        else
            echo "No database yet"
        fi
        ;;

    db)
        command -v sqlite3 >/dev/null 2>&1 || { echo "ERROR: sqlite3 not found."; exit 1; }
        if [ -f "$DB" ]; then
            set +e
            sqlite3 "$DB"
        else
            echo "No database yet"
        fi
        ;;

    help|--help|-h)
        usage
        ;;

    *)
        echo "Unknown command: ${1:-}"
        echo ""
        usage
        exit 1
        ;;
esac
