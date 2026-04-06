#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║  BOTWAVE — One-Command Startup                                  ║
# ║  Run this on your headless machine to launch everything.        ║
# ║                                                                  ║
# ║  Usage: ./botwave-start.sh                                      ║
# ║         ./botwave-start.sh --stop                                ║
# ║         ./botwave-start.sh --status                              ║
# ╚══════════════════════════════════════════════════════════════════╝

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
C="\033[96m"; G="\033[92m"; Y="\033[93m"; R="\033[91m"; M="\033[95m"; W="\033[0m"

log()  { echo -e "$(date +%H:%M:%S) ${C}[*]${W} $1"; }
ok()   { echo -e "$(date +%H:%M:%S) ${G}[+]${W} $1"; }
warn() { echo -e "$(date +%H:%M:%S) ${Y}[!]${W} $1"; }
err()  { echo -e "$(date +%H:%M:%S) ${R}[X]${W} $1"; }

PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/logs"
DATA_DIR="$SCRIPT_DIR/data"
mkdir -p "$PID_DIR" "$LOG_DIR" "$DATA_DIR"

# ── DETECT OLLAMA vs LM STUDIO ──
detect_llm() {
    # Check Ollama first (port 11434)
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "ollama"
        return 0
    fi
    # Check LM Studio (port 1234)
    if curl -s http://localhost:1234/v1/models >/dev/null 2>&1; then
        echo "lmstudio"
        return 0
    fi
    echo "none"
    return 1
}

get_llm_url() {
    local backend=$(detect_llm)
    case "$backend" in
        ollama)   echo "http://localhost:11434/v1" ;;
        lmstudio) echo "http://localhost:1234/v1" ;;
        *)        echo "http://localhost:11434/v1" ;;
    esac
}

get_llm_model() {
    local backend=$(detect_llm)
    case "$backend" in
        ollama)
            # Get the first loaded model from Ollama
            local model=$(curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    models=d.get('models',[])
    if models:
        print(models[0]['name'])
    else:
        print('llama3.1:8b')
except:
    print('llama3.1:8b')
" 2>/dev/null)
            echo "$model"
            ;;
        lmstudio)
            echo "local-model"
            ;;
        *)
            echo "llama3.1:8b"
            ;;
    esac
}

# ── STOP ──
do_stop() {
    echo ""
    echo -e "  ${R}Stopping Botwave...${W}"
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        local name=$(basename "$pidfile" .pid)
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            ok "Stopped $name (PID $pid)"
        fi
        rm -f "$pidfile"
    done
    echo ""
    ok "All services stopped."
}

# ── STATUS ──
do_status() {
    echo ""
    echo -e "  ${M}═══ BOTWAVE STATUS ═══${W}"
    echo ""

    # LLM backend
    local backend=$(detect_llm)
    if [ "$backend" != "none" ]; then
        ok "LLM Backend: $backend ($(get_llm_url))"
        ok "  Model: $(get_llm_model)"
    else
        err "LLM Backend: NOT RUNNING"
        warn "  Start Ollama: ollama serve &"
    fi

    # GPU
    if command -v nvidia-smi &>/dev/null; then
        local gpu_info=$(nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
        if [ -n "$gpu_info" ]; then
            ok "GPU: $gpu_info"
        fi
    fi

    # Dashboard
    if [ -f "$PID_DIR/dashboard.pid" ] && kill -0 "$(cat "$PID_DIR/dashboard.pid")" 2>/dev/null; then
        ok "Dashboard: Running (PID $(cat "$PID_DIR/dashboard.pid"))"
    else
        err "Dashboard: Not running"
    fi

    # Telegram bot
    if [ -f "$PID_DIR/telegram-bot.pid" ] && kill -0 "$(cat "$PID_DIR/telegram-bot.pid")" 2>/dev/null; then
        ok "Telegram Bot: Running (PID $(cat "$PID_DIR/telegram-bot.pid"))"
    else
        warn "Telegram Bot: Not running (set BOTWAVE_MASTER_TOKEN in .env)"
    fi

    # Database
    if [ -f "$DATA_DIR/botwave.db" ]; then
        local db_size=$(du -h "$DATA_DIR/botwave.db" | cut -f1)
        ok "Database: $DATA_DIR/botwave.db ($db_size)"
    else
        warn "Database: Not initialized"
    fi

    echo ""
}

# ── START ──
do_start() {
    echo ""
    echo -e "  ${C}╔══════════════════════════════════════════════════════════════╗${W}"
    echo -e "  ${C}║          BOTWAVE — Starting All Services                     ║${W}"
    echo -e "  ${C}╚══════════════════════════════════════════════════════════════╝${W}"
    echo ""

    # Kill any existing instances
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        local pid=$(cat "$pidfile")
        kill "$pid" 2>/dev/null || true
        rm -f "$pidfile"
    done

    # Load .env if exists
    if [ -f "$SCRIPT_DIR/.env" ]; then
        log "Loading .env configuration..."
        set -a
        source "$SCRIPT_DIR/.env"
        set +a
        ok "Environment loaded"
    elif [ -f "$SCRIPT_DIR/config/.env.example" ]; then
        warn "No .env file found. Copy config/.env.example to .env and fill in your values."
        warn "  cp config/.env.example .env"
    fi

    # ── Check 1: LLM Backend ──
    log "Checking LLM backend..."
    local backend=$(detect_llm)
    if [ "$backend" = "none" ]; then
        warn "No LLM backend detected. Trying to start Ollama..."
        if command -v ollama &>/dev/null; then
            ollama serve &>/dev/null &
            sleep 3
            backend=$(detect_llm)
        fi
    fi

    if [ "$backend" != "none" ]; then
        local llm_url=$(get_llm_url)
        local llm_model=$(get_llm_model)
        ok "LLM Backend: $backend"
        ok "  URL: $llm_url"
        ok "  Model: $llm_model"
        export LLM_API_URL="$llm_url"
        export LLM_MODEL="$llm_model"
    else
        err "No LLM backend available!"
        warn "Install Ollama: curl -fsSL https://ollama.com/install.sh | sh"
        warn "Then: ollama pull llama3.1:8b"
        warn "Botwave will start but AI features won't work until LLM is running."
        export LLM_API_URL="http://localhost:11434/v1"
        export LLM_MODEL="llama3.1:8b"
    fi

    # ── Check 2: GPU ──
    if command -v nvidia-smi &>/dev/null; then
        local gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        local gpu_mem=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
        ok "GPU: $gpu_name (${gpu_mem}MiB VRAM)"
    else
        warn "No NVIDIA GPU detected. AI will be slower on CPU."
    fi

    # ── Check 3: Python ──
    log "Checking Python dependencies..."
    if ! python3 -c "import flask" 2>/dev/null; then
        warn "Installing Python dependencies..."
        pip3 install -r requirements.txt --break-system-packages -q 2>/dev/null || \
        pip3 install -r requirements.txt -q 2>/dev/null || \
        warn "Could not auto-install. Run: pip3 install -r requirements.txt"
    fi
    ok "Python dependencies OK"

    # ── Check 4: Database ──
    log "Initializing database..."
    export DATABASE_PATH="${DATABASE_PATH:-$DATA_DIR/botwave.db}"
    python3 -c "
import sys; sys.path.insert(0, '.')
from src.core.database import Database
from src.core.schema_v2 import apply_v2_schema
db = Database('$DATABASE_PATH')
apply_v2_schema(db)
" 2>/dev/null
    ok "Database ready: $DATABASE_PATH"

    # ── Start Dashboard ──
    log "Starting dashboard..."
    export API_SECRET_KEY="${API_SECRET_KEY:-$(python3 -c 'import secrets;print(secrets.token_hex(32))')}"
    export API_HOST="${API_HOST:-0.0.0.0}"
    export API_PORT="${API_PORT:-5000}"

    # Use v2 (secured) if available, otherwise v1
    local dashboard_file="dashboard/web_app.py"
    if [ -f "dashboard/web_app_v2.py" ]; then
        dashboard_file="dashboard/web_app_v2.py"
        ok "Using secured dashboard (v2)"
    fi

    python3 "$dashboard_file" >> "$LOG_DIR/dashboard.log" 2>&1 &
    echo $! > "$PID_DIR/dashboard.pid"
    sleep 2

    if kill -0 "$(cat "$PID_DIR/dashboard.pid")" 2>/dev/null; then
        ok "Dashboard running on http://$API_HOST:$API_PORT"
    else
        err "Dashboard failed to start. Check $LOG_DIR/dashboard.log"
    fi

    # ── Start Telegram Bot (if token is set) ──
    local bot_token="${BOTWAVE_MASTER_TOKEN:-${TG_PLUMBING_BOT_TOKEN:-}}"
    if [ -n "$bot_token" ]; then
        log "Starting Telegram bot..."
        export BOTWAVE_MASTER_TOKEN="$bot_token"
        python3 -m src.agents.construction_master >> "$LOG_DIR/telegram-bot.log" 2>&1 &
        echo $! > "$PID_DIR/telegram-bot.pid"
        sleep 2

        if kill -0 "$(cat "$PID_DIR/telegram-bot.pid")" 2>/dev/null; then
            ok "Telegram bot running"
        else
            err "Telegram bot failed. Check $LOG_DIR/telegram-bot.log"
        fi
    else
        warn "Telegram bot not started (BOTWAVE_MASTER_TOKEN not set)"
        warn "  Get a token from @BotFather on Telegram"
        warn "  Add to .env: BOTWAVE_MASTER_TOKEN=your-token"
    fi

    # ── Summary ──
    echo ""
    echo -e "  ${G}╔══════════════════════════════════════════════════════════════╗${W}"
    echo -e "  ${G}║  ✅ BOTWAVE IS RUNNING                                       ║${W}"
    echo -e "  ${G}╚══════════════════════════════════════════════════════════════╝${W}"
    echo ""
    echo -e "  ${C}Dashboard:${W}  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):$API_PORT"
    echo -e "  ${C}LLM:${W}        $backend ($llm_model)"
    echo -e "  ${C}Database:${W}   $DATABASE_PATH"
    echo -e "  ${C}Logs:${W}       $LOG_DIR/"
    echo ""
    echo -e "  Stop:   ${Y}./botwave-start.sh --stop${W}"
    echo -e "  Status: ${Y}./botwave-start.sh --status${W}"
    echo ""
}

# ── MAIN ──
case "${1:-}" in
    --stop|-s)    do_stop ;;
    --status|-st) do_status ;;
    --help|-h)
        echo "Usage: ./botwave-start.sh [--stop|--status|--help]"
        echo "  No args: Start all Botwave services"
        echo "  --stop:  Stop all services"
        echo "  --status: Show current status"
        ;;
    *) do_start ;;
esac
