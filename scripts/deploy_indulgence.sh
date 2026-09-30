#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${1:-indulgence}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================================="
echo " Deploying AVB Builder to $TARGET_HOST"
echo "=========================================================="

echo "1. Checking SSH connection to $TARGET_HOST..."
ssh -o ConnectTimeout=5 "$TARGET_HOST" "uname -a"

echo "2. Ensuring /data/avb-builder directory structure on $TARGET_HOST..."
ssh "$TARGET_HOST" "sudo mkdir -p /data/avb-builder/keys /data/avb-builder/storage /data/avb-builder/www/ota /data/avb-builder/www/builds /data/avb-builder/app && sudo chown -R gmglbn_0:users /data/avb-builder"

echo "3. Syncing application files to $TARGET_HOST..."
rsync -avz --exclude '.git' --exclude 'data' --exclude 'bin' "$ROOT_DIR/" "$TARGET_HOST:/data/avb-builder/app/"

if [[ -f "$ROOT_DIR/data/keys/avb.key" ]]; then
    echo "4. Syncing keys to $TARGET_HOST:/data/avb-builder/keys/..."
    rsync -avz "$ROOT_DIR/data/keys/" "$TARGET_HOST:/data/avb-builder/keys/"
    ssh "$TARGET_HOST" "chmod 600 /data/avb-builder/keys/*.key 2>/dev/null || true"
else
    echo "Warning: No local keys found in $ROOT_DIR/data/keys/. Remember to copy avb.key, ota.key, and ota.crt to $TARGET_HOST:/data/avb-builder/keys/!"
fi

echo "5. Building Docker container image on $TARGET_HOST..."
ssh "$TARGET_HOST" "docker build -t avb-builder:latest /data/avb-builder/app"

echo "6. Running container on $TARGET_HOST..."
ssh "$TARGET_HOST" "docker stop avb-builder 2>/dev/null || true && docker rm avb-builder 2>/dev/null || true"
ssh "$TARGET_HOST" "docker run -d \
  --name avb-builder \
  --restart unless-stopped \
  -p 8085:8085 \
  -v /data/avb-builder:/data \
  -e AVB_DATA_DIR=/data \
  -e AVB_PORT=8085 \
  -e AVB_HOST=0.0.0.0 \
  -e AVB_BASE_URL=http://100.64.0.131:8085 \
  avb-builder:latest"

echo ""
echo "=========================================================="
echo " AVB Builder successfully deployed and running on $TARGET_HOST!"
echo " Web Dashboard:  http://100.64.0.131:8085"
echo " Custota URL:    http://100.64.0.131:8085"
echo "=========================================================="
