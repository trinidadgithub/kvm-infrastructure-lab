#!/usr/bin/env bash
set -euo pipefail

# Run as the final guest provisioner, after cloud-init has finished. Packer
# still needs the build SSH key/host keys to authenticate its shutdown command.
cloud-init status --wait

# Cloud-init owns the instance cache, build seed, generated network config and
# machine-id reset. --machine-id writes systemd's 'uninitialized' marker so
# each clone gets its own machine ID on first boot.
cloud-init clean --logs --seed --machine-id --configs network datasource

# Debian's D-Bus machine-id is normally a symlink; replace a standalone copy
# with a symlink so it cannot retain the build VM's identity.
if [[ -f /var/lib/dbus/machine-id && ! -L /var/lib/dbus/machine-id ]]; then
  rm -f -- /var/lib/dbus/machine-id
  ln -s /etc/machine-id /var/lib/dbus/machine-id
fi

# Build SSH credentials are removed by shutdown_command after authentication,
# immediately before poweroff. The next boot regenerates SSH host keys.
rm -f -- /home/ubuntu/.ssh/known_hosts /home/ubuntu/.bash_history /root/.bash_history
rm -rf -- /home/ubuntu/.cache

apt-get clean
rm -rf -- /var/lib/apt/lists/*

# Packer's shell provisioner removes its uploaded scripts (skip_clean=false).
# Do not disable cloud-init or the qemu-guest-agent services.
