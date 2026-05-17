#!/usr/bin/env bash
# Run GC pattern analysis on the production server.
# Usage (from local machine, Git Bash or WSL):
#   bash run_gc_analysis.sh              # default: ranking <= 150, lookback 180d
#   bash run_gc_analysis.sh --ranking 50 --lookback 365

SERVER_USER="alessio9567"
SERVER_HOST="nft_project_server.chickenkiller.com"
SERVER_PORT="2222"
SSH_KEY="$HOME/.ssh/id_rsa"
REMOTE_DIR="/home/alessio9567/nft_project"

EXTRA_ARGS="$*"

ssh -p "$SERVER_PORT" -i "$SSH_KEY" "$SERVER_USER@$SERVER_HOST" \
  "cd $REMOTE_DIR && python scripts/analyze_gc_patterns.py --ranking 150 $EXTRA_ARGS"
