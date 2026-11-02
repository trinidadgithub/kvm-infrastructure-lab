# Ubuntu Server environment (independent state)

This Terraform root manages two Ubuntu 24.04 guests on a dedicated libvirt NAT network and in a dedicated `dir` pool, as reported by the operator. It does not reference the K3s root, its state, network or pool. The VM map in `terraform.tfvars.example` is adjustable; it is not an inventory of running VMs. The existing `terraform/` K3s root remains where it is. For the current operational baseline, PTY issue and Makefile P0 safety notice, start with [engineering continuity](../../docs/ENGINEERING-CONTINUITY.md).

## Storage decision and ownership

For **this workstation**, the host-owned ZFS pool `kvmpool` on the separate 1 TB HDD is reported ONLINE and mounted at `/var/lib/libvirt/images/labs`. This supersedes the earlier `rpool/vms` suggestion for this host. The example layout is:

```text
/var/lib/libvirt/images/labs/       # operator-managed kvmpool mountpoint
  base/                             # operator-published immutable images (no Terraform pool)
  ubuntu-servers/                   # Terraform-managed libvirt dir pool: VM overlays and cloud-init ISOs
```

Use **one environment pool**, not a pool covering `base/`. A second base-image pool offers no benefit while the module takes an absolute backing path, and a Terraform-owned pool over `base/` would blur image-retention responsibility. The dataset and `base/` must exist, be mounted and have appropriate parent-directory traversal permissions before deployment; Terraform must only create/own the `ubuntu-servers/` pool. Do not aim a pool at the dataset mountpoint or put a backing image inside the environment pool. Keep the base and overlays on the same mounted dataset if desired, but qcow2 backing paths are absolute: never move or overwrite a base while overlays exist. Confirm provider pool-destroy behavior on this host before any later destroy, especially for a nonempty directory. No ZFS dataset, quota, reservation or host permissions are created by this repository.

**Storage status:** the operator reports that the WD1003FZEX 1 TB HDD passed its extended SMART self-test and `kvmpool` is ONLINE with an import cache. The earlier disk-initialization approval gate was for creation of this pool; **do not** reinitialize or repartition it. Confirm the actual mount and free capacity before building or publishing. A workstation without a dedicated disk or ZFS must choose a different host-owned storage path; the Terraform pool and `base_image` paths are configurable.

`cloudinit_disk` generates an ISO outside libvirt; the new root sets `cloudinit_in_pool = true`, which creates `module.compute.libvirt_volume.cloudinit_iso[<vm>]` by uploading the generated ISO and attaches the **pool-owned copy**, not the temporary path, to each Ubuntu domain. References give `cloudinit_disk → pool volume → domain` and `pool → pool volume`; the generated ISO is needed for initial upload/replacement but is not the persistent domain medium. Temporary file cleanup should therefore not remove the attached pool volume. The K3s root leaves the new option at its default `false`: its original `vm_disk`, `commoninit` and `vm` resource addresses and its direct ISO attachment remain unchanged. The K3s `lab` pool/network and the Ubuntu `ubuntu-servers` pool/network are declared in separate roots; neither state owns the other's storage. **This is a static graph review**, not proof of provider copy/persistence or QEMU access: after a separately reviewed deployment, verify libvirt pool volumes, domain XML CD-ROM/disk paths, cloud-init success on reboot after temporary-file cleanup, and the effect of `ignore_changes = [devices]` on attachment drift. Check temporary directory capacity and permissions on the host.

The two example virtual disks total 40 GiB *virtual* capacity, not 40 GiB of immediate ZFS use. qcow2 overlays are thin-provisioned; guest writes, qcow2 metadata, two image copies during publication, ZFS snapshots and retention can still exhaust the HDD pool. After its usable capacity and other workloads are known, evaluate a quota and minimum free-space policy for `kvmpool` based on image/guest growth and snapshots; do not configure either without separate approval. A quota below guest growth requirements causes guest I/O failures rather than safely resizing virtual disks. Monitor `zpool list`, `zfs list`, `df`, `du`, snapshots and SMART results. The earlier ~49 GiB free estimate applies to **`rpool`**, not the proposed new pool; building the image or placing temporary files on `rpool` still consumes that space.

## Operator preflight on the **target** workstation (read-only)

1. Verify the host-owned pool is ONLINE and mounted where expected: `findmnt --mountpoint /var/lib/libvirt/images/labs`, `ls -ld /var/lib/libvirt/images/labs /var/lib/libvirt/images/labs/base`, `zfs list -o name,mountpoint,used,avail`, `zpool list`. Confirm `/var/lib/libvirt/images/labs/ubuntu-servers` does **not** already belong to another pool or data owner. Do not reinitialize the disk or run Terraform against a pre-existing unmanaged libvirt pool with the same name.
2. Verify the configured host network, bridge and IPs are free: `virsh -c qemu:///system net-list --all`, `ip -4 route`, `ip -br addr`, `ip link show virbr2`, and check VPN routes. `192.168.124.0/24` must not overlap the default `192.168.122.0/24`, host routes or VPN traffic. Check MAC/domain names with `virsh list --all` and existing libvirt XML. Change `terraform.tfvars` if there is a conflict.
3. Check `getent group libvirt-qemu`, `id`, `virsh -c qemu:///system pool-list --all` and filesystem ownership/traversal (`namei -l` on the published base path and pool parent). Set `pool_group_id` to the **locally resolved** group ID, not a copied value. Do not change global `/var/lib/libvirt/images` permissions. The Terraform pool resource specifies root owner, this group and mode `0770` on its *own* target directory; validate actual libvirt volume permissions separately.
4. Confirm Packer output with `qemu-img info --output=json packer/output-ubuntu2404/<actual-image-filename>` before publishing: format must be qcow2, no backing file and virtual capacity <= the configured guest disks (20 GiB in the example). Ensure the actual image is cloneable and cleaned of build cloud-init/SSH state. Use [Packer publication](../../packer/README.md), and inspect `qemu-img info --backing-chain <overlay>` after a later deployment. Terraform will not build or publish the image.
5. Check AppArmor confinement: `aa-status`, active libvirt/QEMU profiles and libvirt logs. The original host override `etc/apparmor.d/local/abstractions/libvirt-qemu` allows **only** `/var/lib/libvirt/images/lab/`; it does not cover `/var/lib/libvirt/images/labs/base/` or the new pool. The operator must ensure the host's libvirt-generated domain profiles permit reading the published `.qcow2` and writing overlays/`.iso` under the new path, or install a narrowly scoped local policy. Verify access under confinement with an actual test guest later; `terraform validate` cannot check AppArmor or file permissions. Keep traversal rights on every parent directory.
6. Confirm `ssh_public_key_path` exists on the Terraform workstation and matches an available private key for Ansible (`ANSIBLE_PRIVATE_KEY_FILE` or ssh-agent). Ensure the published image path exists, is readable by the libvirt/QEMU runtime, and stays immutable. Check `df -h` on dataset and temporary paths.

The supplied workstation facts (Ubuntu 24.04.5, 16 CPUs, 62 GiB RAM, ZFS `rpool` ~49 GiB free, `kvmpool` ONLINE on a 1 TB HDD, default NAT network) are operator-reported; these checks must be repeated on the host immediately before deployment. This repository has not run them on that workstation. The example `pool_path`/`base_image` values refer to the reported `kvmpool` mountpoint; the `ubuntu-servers` libvirt pool is separately managed by Terraform.

## Inputs, state and commands

Copy `terraform.tfvars.example` to `terraform.tfvars` on the target host; change placeholders, image path, key, addresses, names and resources as necessary. The example uses `ubuntu-servers-net`, `virbr2`, `192.168.124.0/24`, `.10`/`.11` reservations and separate pool `ubuntu-servers`. `pool_group_id`, `base_image`, `ssh_public_key_path` and `vms` are required. The root derives DHCP reservations and the `vm_ips` output from the **same** VM map. That output represents declared addresses, not observed leases. Disk sizing must be at least the published image's virtual capacity (the example uses 20 GiB). No Kubernetes software is installed by the generic cloud-init or playbook.

From repository root, after supplying inputs and image:

```sh
make ENV=ubuntu-servers env-info
make ENV=ubuntu-servers env-tf-init
make ENV=ubuntu-servers env-tf-fmt-check
make ENV=ubuntu-servers env-tf-validate
# In a separate deployment review: make ENV=ubuntu-servers env-tf-plan
```

`env-tf-apply` and `env-tf-destroy` are explicit operator actions; no target runs them automatically. The Phase 2 controller requires a reviewed local `.local-tools.json`, `ENV=ubuntu-servers` on the command line and exact terminal input `apply ubuntu-servers` or `destroy ubuntu-servers`, respectively. This authorization is separate from reviewing the plan; Terraform may ask for its own approval too. Legacy `make tf-*`, `make up`, and `make ansible-site` remain K3s-only and reject an Ubuntu environment selection. The new root's local state is `environments/ubuntu-servers/terraform.tfstate`, ignored by Git; protect and back it up outside the checkout. Never copy the original workstation's K3s state to this host. See the [controller runbook](../../docs/OPERATION-CONTROLLER.md) before operational use.

For a **separately approved** VM snapshot, select exactly one state-owned domain, for example `make ENV=ubuntu-servers VM=ubuntu-server-01 snapshot`. The Phase 2 target checks membership in this root's `vm_names` output and matches `vm_uuids` to `virsh -c qemu:///system domuuid` before requesting `snapshot ubuntu-servers ubuntu-server-01`. It never snapshots all running VMs. The target is intentionally limited to local `qemu:///system`; remote provider URIs require a separately reviewed solution. Account for qcow2/ZFS snapshot growth; this is not a guest-data backup or a disposable test of existing servers.

After the first apply, `make ENV=ubuntu-servers env-state-backup` creates a timestamped local state copy (also ignored by Git); separately keep an off-workstation backup.

After a separately reviewed deployment, `ansible/inventories/ubuntu-servers.py` reads this root's `vm_ips` output. Set `ANSIBLE_PRIVATE_KEY_FILE` or use an ssh-agent, then run `make ENV=ubuntu-servers env-ansible-inventory` and, when intended, `make ENV=ubuntu-servers env-ansible-site`. An offline inventory/syntax check before apply uses the clearly marked **example**, not real outputs:

```sh
export UBUNTU_SERVERS_OUTPUTS_FILE="$PWD/ansible/inventories/ubuntu-servers.outputs.example.json"
make ENV=ubuntu-servers env-ansible-inventory
make ENV=ubuntu-servers env-ansible-syntax
unset UBUNTU_SERVERS_OUTPUTS_FILE
```

In the **uncommitted working tree**, `ansible/playbooks/ubuntu-servers.yaml` calls `ubuntu_baseline` for common OS packages and a running/enabled qemu-guest-agent; the last reported run had `changed=0 failed=0` for both VMs. The playbook never calls the K3s site. When changing DHCP assignments, update root inputs and re-run inventory from outputs, not from an independently maintained IP list. Output-driven inventory needs applied state; the offline fixture verifies only script format and playbook parsing. Review role changes in check mode before any approved execution.

The existing K3s version remains `v1.32.0` in the two K3s inventory group-var files; it is no longer a variable for generic Ubuntu hosts.

## Remaining deployment gates

The operator reports that the published v1 image and two existing guests have passed boot/cloud-init/SSH/guest-agent checks and that a later plan was clean. Before **new** VM creation, verify storage free space, image checksum and AppArmor/access, choose collision-free identities, and review the plan and provider PTY risk described in [engineering continuity](../../docs/ENGINEERING-CONTINUITY.md). Neither `terraform validate` nor the reported clean plan verifies the untested initial-creation console workaround or device drift hidden by `ignore_changes = [devices]`.
