# Ubuntu 24.04 image: build, seal, publish

Packer's QEMU builder (plugin v1.1.7) boots a clone of the pinned Ubuntu cloud qcow2 (`disk_image = true`, without a backing file); there is no installer or keyboard boot command. The attached, host-side NoCloud `seed.iso` sets up the `ubuntu` account and SSH key for provisioning; it is **not** copied into the guest disk. The builder runs provisioning via SSH, runs `seal-image.sh` as its last provisioner and sends an authenticated `shutdown_command` that removes build SSH credentials before `shutdown -P now`. A shutdown timeout is an error, not a reason to silently accept a forced halt. `output_directory` is relative to Packer's working directory; Make always changes into `packer/`. `path.root` supplies the seed and sealing-script paths independently of the caller's working directory.

## Before the build

Use an **unencrypted** dedicated SSH build key stored outside Git. `PKR_VAR_ssh_private_key` must be its absolute path: both the Packer communicator and `create-seed.sh` use it; the seed script derives the matching public key with `ssh-keygen -y`, so an unrelated `.pub` cannot be selected. Never put a private key in a `.pkrvars.hcl` tracked file. Have `cloud-localds` (package `cloud-image-utils`) or `genisoimage`, `ssh-keygen`, QEMU/KVM and the Packer QEMU plugin installed. `packer init` installs the plugin. The seed generator writes a disposable `packer/seed.iso` with label `cidata`, `user-data` and `meta-data`, and replaces it for each build; `.gitignore` excludes it. A nondefault absolute `PACKER_SEED_OUTPUT` is for offline seed tests only; the Packer builder expects `packer/seed.iso`.

From the repository root, after choosing your own key path:

```sh
export PKR_VAR_ssh_private_key="$(realpath "$HOME/.ssh/<build-key>")"
make packer-init
make packer-fmt-check
make packer-validate        # regenerates packer/seed.iso; does not boot a VM
# After reviewing the build separately:
make packer-build           # regenerates the seed again; boots and seals the build VM
```

`base_image_url` and `base_image_checksum` in `variables.pkr.hcl` are used by the builder; Packer verifies the explicit SHA-256. If the upstream `/release/` URL changes, stop and independently verify the new source and checksum before deliberately updating the pinned value; never disable checksum verification. `packer validate` checks configuration, not the remote image contents or whether boot, package installation, shutdown and sealing succeed. Avoid concurrent builds in the same output directory. Never run `packer build -force` against an output directory containing an image you intend to retain.

## Seal and inspect the build output

The final guest provisioner waits for cloud-init to finish, calls `cloud-init clean --logs --seed --machine-id --configs network datasource`, clears build user history/cache and apt lists, and retains cloud-init, qemu-guest-agent and installed packages. Packer removes its uploaded shell scripts by default. **Build SSH authentication stays available through provisioner cleanup**; after Packer authenticates for shutdown, the shutdown command removes the injected authorized key and SSH host keys, then powers off. If this command fails, do not use the output image. Cloud-init's first-boot SSH module and systemd should regenerate distinct host keys and machine IDs in new VMs. The mounted build seed ISO is host-side temporary media; Terraform attaches **different** guest-specific cloud-init media later.

After an **operator-run** build, inspect the actual artifact before publication:

```sh
qemu-img info --output=json packer/output-ubuntu2404/ubuntu-24.04-lab-base.qcow2
qemu-img check -f qcow2 packer/output-ubuntu2404/ubuntu-24.04-lab-base.qcow2
```

Verify format qcow2, *no backing file*, and virtual capacity no larger than each VM overlay (20 GiB in the example). Boot a disposable guest with its own NoCloud seed, confirm a unique machine ID and new SSH host keys, cloud-init status, correct guest hostname/SSH access and working guest agent. Static checks and a successful Packer build **cannot** substitute for this clone-and-boot test; verify that no build key or NoCloud instance cache survived in the resulting guest.

## Publish, separately

On the specified workstation, `kvmpool` is reported ONLINE at `/var/lib/libvirt/images/labs`; the operator owns the `base/` directory. After verifying its mount, free space, libvirt read/traversal permissions and AppArmor access, publish the checked artifact as a **new** version:

```sh
bin/publish-image packer/output-ubuntu2404/ubuntu-24.04-lab-base.qcow2 \
  /var/lib/libvirt/images/labs/base v1
```

The expected output is `/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2`. The script checks qcow2 integrity, compares the source and temporary copy SHA-256, then atomically links a versioned filename. It refuses to overwrite an existing destination and cleans temporary copies on failure. Record its printed SHA-256, source Ubuntu URL/checksum and image path; configure `base_image` in `environments/ubuntu-servers/terraform.tfvars` to this absolute path. Do not rebuild and publish automatically as part of Terraform deployment.

Mode `0444` discourages accidental writes but is **not absolute immutability**: an owner can change permissions and privileged processes can replace the image. Retain old images and checksums while any overlay or restore references them. A newer image requires a separately planned VM rebuild/data migration. Other workstations can use a different host-owned publication directory; avoid assuming they use ZFS. Check space for the cloud image download, build output, copy and snapshots on the relevant filesystems.
