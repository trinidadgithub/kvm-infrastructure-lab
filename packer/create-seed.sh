#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${PACKER_SEED_OUTPUT:-${DIR}/seed.iso}"
PRIVATE_KEY="${PKR_VAR_ssh_private_key:-}"

if [[ -z "$PRIVATE_KEY" || "$PRIVATE_KEY" != /* || ! -f "$PRIVATE_KEY" ]]; then
  echo "Set PKR_VAR_ssh_private_key to an absolute path to an unencrypted private key" >&2
  exit 1
fi
if [[ "$OUT" != /* ]]; then
  echo "PACKER_SEED_OUTPUT must be an absolute path" >&2
  exit 1
fi
if ! command -v cloud-localds >/dev/null && ! command -v genisoimage >/dev/null; then
  echo "Install cloud-image-utils (cloud-localds) or genisoimage to create the NoCloud seed" >&2
  exit 1
fi

# Deriving the public key, rather than selecting an unrelated *.pub, guarantees
# that the NoCloud authorized key matches Packer's SSH communicator identity.
if ! PUBLIC_KEY="$(ssh-keygen -y -P '' -f "$PRIVATE_KEY")"; then
  echo "Unable to derive public key from $PRIVATE_KEY (use an unencrypted build key)" >&2
  exit 1
fi

umask 077
TEMP_DIR="$(mktemp -d "${OUT}.tmp.XXXXXXXX")"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

cat > "$TEMP_DIR/user-data" <<EOF
#cloud-config
hostname: packer-build
manage_etc_hosts: true
users:
  - name: ubuntu
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: users
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - ${PUBLIC_KEY}
ssh_pwauth: false
disable_root: true
EOF

cat > "$TEMP_DIR/meta-data" <<'EOF'
instance-id: iid-packer-build
local-hostname: packer-build
EOF

if command -v cloud-localds >/dev/null; then
  cloud-localds "$TEMP_DIR/seed.iso" "$TEMP_DIR/user-data" "$TEMP_DIR/meta-data"
else
  genisoimage -quiet -volid cidata -joliet -rock -output "$TEMP_DIR/seed.iso" \
    -graft-points "user-data=$TEMP_DIR/user-data" "meta-data=$TEMP_DIR/meta-data"
fi

mv -f -- "$TEMP_DIR/seed.iso" "$OUT"
echo "NoCloud seed ISO created: $OUT"
