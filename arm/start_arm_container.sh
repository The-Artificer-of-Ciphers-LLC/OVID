#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# ARM container start script — with OVID integration
# ══════════════════════════════════════════════════════════════════
# Deploy to: /home/arm/start_arm_container.sh on holodeck
#
# This template extends the standard ARM docker-run invocation with:
#   • --network ovid_default    → ARM can reach the OVID API container
#   • Volume mounts for OVID    → identify_ovid.py, identify.py shim,
#                                  and entrypoint_wrapper.sh
#   • --entrypoint wrapper      → installs ovid-client and backs up the
#                                  original identify.py at first boot
#   • OVID_ENABLED env var      → toggles the OVID lookup on/off
#
# ── OPERATOR SETUP ──────────────────────────────────────────────
# 1. Copy these files from the OVID repo's arm/ directory to OVID_DIR:
#       arm/identify_ovid.py
#       arm/identify.py
#       arm/entrypoint_wrapper.sh
#    Example:
#       scp arm/identify_ovid.py arm/identify.py arm/entrypoint_wrapper.sh \
#           holodeck:/home/arm/ovid/
#
# 2. Make the entrypoint wrapper executable:
#       chmod +x /home/arm/ovid/entrypoint_wrapper.sh
#
# 3. Ensure the OVID stack is running (docker compose up -d in the
#    OVID project directory) so the 'ovid_default' network exists.
#
# 4. Run this script to start ARM with OVID integration.
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────
OVID_DIR="/home/arm/ovid"
CONTAINER_NAME="arm-rippers"
ARM_IMAGE="automaticrippingmachine/arm-rippers:latest"

# ── Pre-flight checks ────────────────────────────────────────────
if [ ! -f "$OVID_DIR/identify_ovid.py" ]; then
    echo "ERROR: $OVID_DIR/identify_ovid.py not found."
    echo "Copy the OVID integration files to $OVID_DIR first."
    exit 1
fi

if [ ! -f "$OVID_DIR/entrypoint_wrapper.sh" ]; then
    echo "ERROR: $OVID_DIR/entrypoint_wrapper.sh not found."
    exit 1
fi

chmod +x "$OVID_DIR/entrypoint_wrapper.sh"

# ── Stop existing container if running ───────────────────────────
if docker ps -q --filter "name=$CONTAINER_NAME" | grep -q .; then
    echo "Stopping existing $CONTAINER_NAME container..."
    docker stop "$CONTAINER_NAME"
    docker rm "$CONTAINER_NAME"
fi

# ── Start ARM container with OVID integration ────────────────────
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    \
    `# ── Network: join the OVID compose network so ARM can reach` \
    `#    the OVID API at http://api:8000 ──` \
    --network ovid_default \
    \
    `# ── OVID environment ──` \
    -e OVID_ENABLED=true \
    -e OVID_API_URL=http://api:8000 \
    \
    `# ── OVID volume mounts ──` \
    `# identify_ovid.py: standalone OVID fingerprint lookup module` \
    -v "$OVID_DIR/identify_ovid.py:/opt/arm/arm/ripper/identify_ovid.py:ro" \
    \
    `# identify.py: OVID shim that hooks into ARM's identify flow` \
    -v "$OVID_DIR/identify.py:/opt/arm/arm/ripper/identify.py:ro" \
    \
    `# entrypoint_wrapper.sh: installs ovid-client and backs up` \
    `# the original identify.py before ARM starts` \
    -v "$OVID_DIR/entrypoint_wrapper.sh:/entrypoint_wrapper.sh:ro" \
    \
    `# ── ARM's standard mounts (operator: add your existing mounts here) ──` \
    `# -v /home/arm/.MakeMKV:/root/.MakeMKV` \
    `# -v /home/arm/media:/home/arm/media` \
    `# -v /home/arm/config:/etc/arm/config` \
    `# --device /dev/sr0:/dev/sr0` \
    `# --privileged` \
    \
    `# ── Entrypoint: run the wrapper, which then calls ARM's /init ──` \
    --entrypoint /entrypoint_wrapper.sh \
    "$ARM_IMAGE" \
    /opt/arm/scripts/init  # ARM's original entrypoint — passed as CMD

echo "✅ $CONTAINER_NAME started with OVID integration on network ovid_default"
echo "   OVID API: http://api:8000"
echo "   Verify:   docker exec $CONTAINER_NAME python3 -c 'from identify_ovid import lookup_ovid; print(\"OK\")'"
