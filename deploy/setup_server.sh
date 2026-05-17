#!/usr/bin/env bash
# =============================================================================
# setup_server.sh — One-time setup for NFT ML pipeline on Linux (Ubuntu/Debian)
#
# Run as root:  sudo bash deploy/setup_server.sh
#
# What this does:
#   1. Installs system dependencies (Python 3.11, git, sqlite3)
#   2. Creates a dedicated 'nft' system user
#   3. Copies the project to /opt/nft_project
#   4. Creates and populates the Python virtualenv
#   5. Creates log directories and sets permissions
#   6. Installs and enables the systemd service + timer
#   7. Prints a checklist of manual steps (secrets, .env)
# =============================================================================

set -euo pipefail

PROJECT_DIR="/opt/nft_project"
SERVICE_USER="nft"
LOG_DIR="/var/log/nft_ml"
PYTHON_BIN="python3.11"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Run as root: sudo bash $0"

info "=== NFT ML Server Setup ==="

# ── 1. System packages ────────────────────────────────────────────────────────
info "Installing system packages ..."
apt-get update -qq
apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip git sqlite3 curl \
    build-essential libssl-dev ca-certificates

# ── 2. Dedicated user ─────────────────────────────────────────────────────────
if ! id "$SERVICE_USER" &>/dev/null; then
    info "Creating system user '$SERVICE_USER' ..."
    useradd --system --shell /bin/bash --home-dir "$PROJECT_DIR" \
            --create-home "$SERVICE_USER"
else
    info "User '$SERVICE_USER' already exists."
fi

# ── 3. Deploy project files ───────────────────────────────────────────────────
info "Deploying project to $PROJECT_DIR ..."

# If running from within the project directory, rsync it over.
# Otherwise, set REPO_URL below and clone from git.
REPO_URL=""   # e.g. "git@github.com:youruser/nft_project.git"

if [[ -n "$REPO_URL" ]]; then
    if [[ -d "$PROJECT_DIR/.git" ]]; then
        info "Pulling latest from git ..."
        sudo -u "$SERVICE_USER" git -C "$PROJECT_DIR" pull --ff-only
    else
        info "Cloning repository ..."
        git clone "$REPO_URL" "$PROJECT_DIR"
        chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"
    fi
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SOURCE_DIR="$(dirname "$SCRIPT_DIR")"
    info "Syncing local files from $SOURCE_DIR ..."
    rsync -a --exclude='.venv' --exclude='__pycache__' \
              --exclude='*.pyc' --exclude='.env' \
              --exclude='nft_data.sqlite3' \
              "$SOURCE_DIR/" "$PROJECT_DIR/"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"
fi

# ── 4. Python virtualenv ──────────────────────────────────────────────────────
VENV="$PROJECT_DIR/.venv"
if [[ ! -d "$VENV" ]]; then
    info "Creating Python virtualenv at $VENV ..."
    sudo -u "$SERVICE_USER" $PYTHON_BIN -m venv "$VENV"
fi

info "Installing Python dependencies ..."
sudo -u "$SERVICE_USER" "$VENV/bin/pip" install --quiet --upgrade pip
sudo -u "$SERVICE_USER" "$VENV/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"

# ── 5. Data directory and log rotation ───────────────────────────────────────
info "Creating data and log directories ..."
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$LOG_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/data" "$LOG_DIR"

# Log rotation config
cat > /etc/logrotate.d/nft_ml <<EOF
$LOG_DIR/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    create 0640 $SERVICE_USER $SERVICE_USER
}
EOF
info "Log rotation configured at /etc/logrotate.d/nft_ml"

# ── 6. Systemd service + timer ────────────────────────────────────────────────
info "Installing systemd units ..."
cp "$PROJECT_DIR/deploy/nft_ml_daily.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/nft_ml_daily.timer"   /etc/systemd/system/

systemctl daemon-reload
systemctl enable nft_ml_daily.timer
systemctl start  nft_ml_daily.timer

info "Timer status:"
systemctl status nft_ml_daily.timer --no-pager || true

# ── 7. Checklist ──────────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  MANUAL STEPS REQUIRED"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  1. Copy your .env file to the server:"
echo "       scp .env user@server:$PROJECT_DIR/.env"
echo "       chown $SERVICE_USER:$SERVICE_USER $PROJECT_DIR/.env"
echo "       chmod 600 $PROJECT_DIR/.env"
echo ""
echo "  2. Copy your database to the server (if not starting fresh):"
echo "       scp nft_data.sqlite3 user@server:$PROJECT_DIR/nft_data.sqlite3"
echo "       chown $SERVICE_USER:$SERVICE_USER $PROJECT_DIR/nft_data.sqlite3"
echo ""
echo "  3. Add ML config vars to your .env (see below):"
echo "       ML_HORIZON=14"
echo "       ML_THRESHOLD=0.10"
echo "       ML_MIN_CONFIDENCE=0.60"
echo "       ML_TOP_N=15"
echo "       ML_MIN_DAYS=60"
echo "       ML_MODEL_PATH=$PROJECT_DIR/data/ml_model.pkl"
echo ""
echo "  4. Run the first training manually:"
echo "       sudo -u $SERVICE_USER $VENV/bin/python $PROJECT_DIR/scripts/daily_ml_run.py --dry-run"
echo ""
echo "  5. Verify the timer schedule:"
echo "       systemctl list-timers nft_ml_daily.timer"
echo ""
echo "  6. Check logs:"
echo "       tail -f $LOG_DIR/daily_ml_run.log"
echo ""
echo -e "${GREEN}Setup complete.${NC}"
