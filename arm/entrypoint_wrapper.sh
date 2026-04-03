#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# ARM container entrypoint wrapper — OVID integration
# ──────────────────────────────────────────────────────────────────
# This script runs *before* ARM's normal /init entrypoint.  It:
#   1. Installs the ovid-client pip package (idempotently).
#   2. Backs up the original identify.py so the OVID shim can
#      delegate to it via identify_original.py.
#   3. Hands off to the original CMD/entrypoint via exec "$@".
#
# Mount this into the container at /entrypoint_wrapper.sh and set
# --entrypoint /entrypoint_wrapper.sh with the original entrypoint
# (/init) as the CMD argument.
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

ARM_IDENTIFY="/opt/arm/arm/ripper/identify.py"
ARM_IDENTIFY_BACKUP="/opt/arm/arm/ripper/identify_original.py"

# ── Step 1: Install ovid-client if not already present ────────────
if ! python3 -c "import ovid" 2>/dev/null; then
    echo "[ovid-entrypoint] Installing ovid-client..."
    pip3 install --quiet ovid-client
fi

# ── Step 2: Back up original identify.py (once) ──────────────────
if [ -f "$ARM_IDENTIFY" ] && [ ! -f "$ARM_IDENTIFY_BACKUP" ]; then
    echo "[ovid-entrypoint] Backing up original identify.py → identify_original.py"
    cp "$ARM_IDENTIFY" "$ARM_IDENTIFY_BACKUP"
fi

echo "[ovid-entrypoint] OVID integration ready — handing off to ARM"

# ── Step 3: Execute the original entrypoint ──────────────────────
exec "$@"
