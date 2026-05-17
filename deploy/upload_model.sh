#!/usr/bin/env bash
# =============================================================================
# upload_model.sh — Push the locally trained model to the Linux server
#
# Run from your local machine (Windows Git Bash, WSL, or macOS/Linux terminal):
#   bash deploy/upload_model.sh
#
# Required env vars (set in .env or export before running):
#   SERVER_USER    SSH username on the server         (e.g. ubuntu)
#   SERVER_HOST    Server IP or hostname               (e.g. 1.2.3.4)
#   SERVER_PATH    Project path on server              (default: /opt/nft_project)
#   SSH_KEY        Path to your SSH private key        (default: ~/.ssh/id_rsa)
#
# What it uploads:
#   data/ml_model.pkl  → ${SERVER_PATH}/data/ml_model.pkl
#   (also reloads the trained_at timestamp from the pickle to log it)
# =============================================================================

set -euo pipefail

# ── Load config ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source .env if it exists (allows setting vars there)
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -v '^\s*#' "$PROJECT_DIR/.env" | grep '=')
    set +a
fi

SERVER_USER="${SERVER_USER:-}"
SERVER_HOST="${SERVER_HOST:-}"
SERVER_PATH="${SERVER_PATH:-/opt/nft_project}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
MODEL_LOCAL="$PROJECT_DIR/data/ml_model.pkl"

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ -z "$SERVER_USER" || -z "$SERVER_HOST" ]]; then
    echo "ERROR: SERVER_USER and SERVER_HOST must be set."
    echo "       Export them or add to your .env file:"
    echo "         SERVER_USER=ubuntu"
    echo "         SERVER_HOST=your.server.ip"
    exit 1
fi

if [[ ! -f "$MODEL_LOCAL" ]]; then
    echo "ERROR: Model file not found: $MODEL_LOCAL"
    echo "       Run training first:"
    echo "         python scripts/train_ml_model.py --no-cv"
    exit 1
fi

MODEL_SIZE=$(du -sh "$MODEL_LOCAL" | cut -f1)
echo "Uploading model: $MODEL_LOCAL ($MODEL_SIZE)"
echo "Destination:     $SERVER_USER@$SERVER_HOST:$SERVER_PATH/data/ml_model.pkl"

# ── Upload ────────────────────────────────────────────────────────────────────
scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
    "$MODEL_LOCAL" \
    "$SERVER_USER@$SERVER_HOST:$SERVER_PATH/data/ml_model.pkl"

# Fix ownership on the server
ssh -i "$SSH_KEY" "$SERVER_USER@$SERVER_HOST" \
    "chown nft:nft $SERVER_PATH/data/ml_model.pkl 2>/dev/null || true"

echo ""
echo "Upload complete."
echo ""
echo "To verify on the server:"
echo "  ssh $SERVER_USER@$SERVER_HOST"
echo "  sudo -u nft /opt/nft_project/.venv/bin/python -c \\"
echo "    \"from app.ml.model import load_model; m,f=load_model(); print('OK, features:', len(f))\""
echo ""
echo "To run prediction immediately (dry run):"
echo "  ssh $SERVER_USER@$SERVER_HOST \\"
echo "    'sudo -u nft /opt/nft_project/.venv/bin/python \\"
echo "     /opt/nft_project/scripts/daily_ml_run.py --skip-train --dry-run'"
