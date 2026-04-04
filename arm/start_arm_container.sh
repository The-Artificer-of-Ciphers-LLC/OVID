#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# ARM container start script — with OVID integration
# ══════════════════════════════════════════════════════════════════
# Deploy to: /home/arm/start_arm_container.sh on holodeck
#
# This script starts the ARM container wired into the OVID Docker
# network (ovid_default) so ARM can reach the OVID API, then also
# connects the default bridge network so the ARM UI is accessible
# on the LAN at http://holodeck:8080.
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
# 2. Build the ovid-client wheel and copy it:
#       scp ovid_client-0.1.0-py3-none-any.whl holodeck:/home/arm/ovid/
#
# 3. Make the entrypoint wrapper executable:
#       chmod +x /home/arm/ovid/entrypoint_wrapper.sh
#
# 4. Ensure the OVID stack is running (docker compose up -d in the
#    OVID project directory) so the 'ovid_default' network exists.
#
# 5. Run this script to start ARM with OVID integration.
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────
OVID_DIR="/home/arm/ovid"
CONTAINER_NAME="arm-rippers"
ARM_IMAGE="automaticrippingmachine/automatic-ripping-machine:latest"

# ── Pre-flight checks ────────────────────────────────────────────
if [ ! -f "$OVID_DIR/identify_ovid.py" ]; then
    echo "ERROR: $OVID_DIR/identify_ovid.py not found."
    echo "Copy the OVID integration files to $OVID_DIR first."
    exit 1
fi

if [ ! -f "$OVID_DIR/identify_original.py" ]; then
    echo "ERROR: $OVID_DIR/identify_original.py not found."
    echo "Extract the original ARM identify.py from the Docker image and save it as identify_original.py."
    exit 1
fi

if [ ! -f "$OVID_DIR/entrypoint_wrapper.sh" ]; then
    echo "ERROR: $OVID_DIR/entrypoint_wrapper.sh not found."
    exit 1
fi

if [ ! -f "$OVID_DIR/ovid_client-0.1.0-py3-none-any.whl" ]; then
    echo "WARNING: $OVID_DIR/ovid_client-0.1.0-py3-none-any.whl not found."
    echo "OVID lookup will be disabled until the wheel is available."
fi

chmod +x "$OVID_DIR/entrypoint_wrapper.sh"

# ── Stop existing container if running ───────────────────────────
if docker ps -aq --filter "name=^${CONTAINER_NAME}$" | grep -q .; then
    echo "Stopping existing $CONTAINER_NAME container..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
fi

# ── Start ARM container with OVID integration ────────────────────
# Start on ovid_default so ARM can reach the OVID API at http://api:8000.
# After start, connect bridge so port 8080 is accessible on the LAN.
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart always \
    --privileged \
    --cpuset-cpus=2-7 \
    \
    `# ── Network: start on default bridge for LAN port binding ──` \
    `# ovid_default is connected post-start so ARM can reach OVID API` \
    \
    `# ── Ports ──` \
    -p 8080:8080 \
    \
    `# ── Device access ──` \
    --device /dev/sr0:/dev/sr0 \
    \
    `# ── ARM environment ──` \
    -e ARM_UID=1001 \
    -e ARM_GID=1002 \
    -e TZ=Etc/UTC \
    \
    `# ── OVID environment ──` \
    -e OVID_ENABLED=true \
    -e OVID_API_URL=http://api:8000 \
    -e OVID_API_TOKEN="${OVID_API_TOKEN:-}" \
    \
    `# ── ARM standard mounts (holodeck paths) ──` \
    -v /home/arm:/home/arm \
    -v /home/arm/music:/home/arm/music \
    -v /home/arm/logs:/home/arm/logs \
    -v /home/arm/media:/home/arm/media \
    -v /home/arm/config:/etc/arm/config \
    \
    `# ── OVID volume mounts ──` \
    -v "$OVID_DIR/identify_ovid.py:/opt/arm/arm/ripper/identify_ovid.py" \
    -v "$OVID_DIR/identify.py:/opt/arm/arm/ripper/identify.py" \
    -v "$OVID_DIR/identify_original.py:/opt/arm/arm/ripper/identify_original.py" \
    -v "$OVID_DIR/entrypoint_wrapper.sh:/entrypoint_wrapper.sh:ro" \
    -v "$OVID_DIR/ovid_client-0.1.0-py3-none-any.whl:/home/arm/ovid/ovid_client-0.1.0-py3-none-any.whl:ro" \
    \
    `# ── Entrypoint: OVID wrapper, then phusion init ──` \
    --entrypoint /entrypoint_wrapper.sh \
    "$ARM_IMAGE" \
    /sbin/my_init

# ── Post-start: connect OVID network for API access ──────────────
echo "Connecting $CONTAINER_NAME to ovid_default network for OVID API access..."
docker network connect ovid_default "$CONTAINER_NAME" 2>/dev/null \
    || echo "WARNING: Could not connect ovid_default network (may already be connected)"

echo ""
echo "✅ $CONTAINER_NAME started with OVID integration"
echo "   Network:  bridge (LAN) + ovid_default (OVID API)"
echo "   OVID API: http://api:8000 (via ovid_default)"
echo "   ARM UI:   http://holodeck:8080"
echo "   Verify:   docker exec $CONTAINER_NAME python3 -c 'from identify_ovid import lookup_ovid; print(\"OK\")'"
