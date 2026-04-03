#!/usr/bin/env bash
# Management script for exchange-rate-bot
set -euo pipefail

SERVICE="exchange-rate-bot"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="${SCRIPT_DIR}/data/bot.db"

usage() {
    echo "Usage: ./bot.sh <command>"
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
    echo "  db        — open sqlite3 shell"
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
        sudo journalctl -u "$SERVICE" -f
        ;;

    log)
        if [ -f "${SCRIPT_DIR}/data/bot.log" ]; then
            tail -50 "${SCRIPT_DIR}/data/bot.log"
        else
            echo "No log file yet. Try: ./bot.sh logs"
        fi
        ;;

    update)
        echo "=== Pulling latest code ==="
        cd "$SCRIPT_DIR"
        git pull
        echo ""
        echo "=== Installing dependencies ==="
        source venv/bin/activate
        pip install -q -r requirements.txt
        echo ""
        echo "=== Restarting ==="
        sudo systemctl restart "$SERVICE"
        sleep 2
        systemctl status "$SERVICE" --no-pager
        ;;

    restart)
        sudo systemctl restart "$SERVICE"
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
        if [ -f "$DB" ]; then
            echo "=== Monthly API Usage ==="
            sqlite3 "$DB" "SELECT month, call_count FROM api_usage ORDER BY month DESC LIMIT 6;"
        else
            echo "No database yet"
        fi
        ;;

    users)
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

    db)
        if [ -f "$DB" ]; then
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
