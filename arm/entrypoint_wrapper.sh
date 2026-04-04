#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# ARM container entrypoint wrapper — OVID integration
# ──────────────────────────────────────────────────────────────────
# This script runs *before* ARM's normal /sbin/my_init entrypoint.  It:
#   1. Installs the ovid-client package from a local wheel
#      (mounted at /home/arm/ovid/ovid_client-0.1.0-py3-none-any.whl).
#   2. Backs up the original identify.py so the OVID shim can
#      delegate to it via identify_original.py.
#   3. Hands off to the original CMD/entrypoint via exec "$@".
#
# Mount this into the container at /entrypoint_wrapper.sh and set
# --entrypoint /entrypoint_wrapper.sh with /sbin/my_init as CMD.
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

ARM_IDENTIFY="/opt/arm/arm/ripper/identify.py"
ARM_IDENTIFY_BACKUP="/opt/arm/arm/ripper/identify_original.py"
OVID_WHEEL="/home/arm/ovid/ovid_client-0.1.0-py3-none-any.whl"

# ── Step 1: Install ovid-client from local wheel if not already present ──
# NOTE: Cannot use `python3 -c "import ovid"` here because /home/arm/ovid/
# directory creates a namespace package that falsely satisfies the import.
# Use pip3 show to check if the *real* wheel-installed package is present.
if ! pip3 show ovid-client >/dev/null 2>&1; then
    echo "[ovid-entrypoint] Installing ovid-client..."
    if [ -f "$OVID_WHEEL" ]; then
        pip3 install --quiet --root-user-action=ignore "$OVID_WHEEL"
    else
        echo "[ovid-entrypoint] WARNING: Wheel not found at $OVID_WHEEL"
        echo "[ovid-entrypoint] WARNING: ovid-client install failed — OVID lookup will be disabled"
    fi
fi

# ── Step 2: Verify original identify.py backup exists ────────────
# The original identify_original.py is deployed alongside identify.py
# (mounted from the host).  We no longer copy at runtime because the
# bind-mount replaces identify.py before the entrypoint runs — a cp
# here would just duplicate the OVID shim.
if [ ! -f "$ARM_IDENTIFY_BACKUP" ]; then
    echo "[ovid-entrypoint] WARNING: identify_original.py not found at $ARM_IDENTIFY_BACKUP"
    echo "[ovid-entrypoint] OVID shim will not be able to fall back to ARM's native identify."
fi

echo "[ovid-entrypoint] OVID integration ready — handing off to ARM"

# ── Step 3: Execute the original entrypoint ──────────────────────
exec "$@"
