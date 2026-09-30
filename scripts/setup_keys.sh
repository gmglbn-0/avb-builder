#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
KEYS_DIR="${1:-$ROOT_DIR/data/keys}"
BIN_DIR="$ROOT_DIR/bin"

mkdir -p "$KEYS_DIR"

AVBROOT="$BIN_DIR/avbroot"
if ! command -v "$AVBROOT" &>/dev/null; then
    if command -v avbroot &>/dev/null; then
        AVBROOT="avbroot"
    else
        echo "Error: avbroot not found in $BIN_DIR or PATH."
        exit 1
    fi
fi

echo "=========================================================="
echo " AVB Builder Key Management Helper"
echo " Target Keys Directory: $KEYS_DIR"
echo "=========================================================="

if [[ -f "$KEYS_DIR/avb.key" && -f "$KEYS_DIR/ota.key" && -f "$KEYS_DIR/ota.crt" ]]; then
    echo "Found existing keys in $KEYS_DIR:"
    ls -la "$KEYS_DIR"
    echo ""
    echo "If you also have avb_pkmd.bin, verify it is present:"
    if [[ -f "$KEYS_DIR/avb_pkmd.bin" ]]; then
        echo "avb_pkmd.bin is present (ready for fastboot flash avb_custom_key)."
    else
        echo "Generating avb_pkmd.bin from avb.key..."
        "$AVBROOT" pkmd generate -k "$KEYS_DIR/avb.key" -o "$KEYS_DIR/avb_pkmd.bin"
        echo "Created $KEYS_DIR/avb_pkmd.bin"
    fi
else
    echo "Existing keys not found in $KEYS_DIR."
    read -rp "Would you like to generate new avbroot keypairs now? [y/N]: " choice
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        echo "1. Generating AVB key..."
        "$AVBROOT" key generate-avb -k "$KEYS_DIR/avb.key"

        echo "2. Generating AVB public key digest (avb_pkmd.bin)..."
        "$AVBROOT" pkmd generate -k "$KEYS_DIR/avb.key" -o "$KEYS_DIR/avb_pkmd.bin"

        echo "3. Generating OTA signing key and certificate..."
        "$AVBROOT" key generate-ota -k "$KEYS_DIR/ota.key" -c "$KEYS_DIR/ota.crt"

        chmod 600 "$KEYS_DIR"/*.key
        echo "Keys generated successfully in $KEYS_DIR."
    else
        echo "Please copy your existing keys into $KEYS_DIR:"
        echo "  - $KEYS_DIR/avb.key"
        echo "  - $KEYS_DIR/ota.key"
        echo "  - $KEYS_DIR/ota.crt"
        echo "  - $KEYS_DIR/avb_pkmd.bin"
    fi
fi
