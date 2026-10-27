# Ubuntu Server environment (independent state)

This Terraform root creates two example Ubuntu 24.04 guests on a dedicated libvirt NAT network and in a dedicated `dir` pool. It does not reference the K3s root, its state, network or pool. The VM map in `terraform.tfvars.example` is adjustable; it is not an inventory of running VMs. The existing `terraform/` K3s root remains where it is.

## Storage decision and ownership

The proposed `rpool/vms` dataset with mountpoint `/var/lib/libvirt/images/labs` is **host-owned**, outside Terraform. The example layout is:

```text
/var/lib/libvirt/images/labs/       # operator-managed ZFS dataset mountpoint
  base/                             # operator-published immutable images (no Terraform pool)
  ubuntu-servers/                   # Terraform-managed libvirt dir pool: VM overlays and cloud-init ISOs
```

Use **one environment pool**, not a pool covering `base/`. A second base-image pool offers no benefit while the module takes an absolute backing path, and a Terraform-owned pool over `base/` would blur image-retention responsibility. The dataset and `base/` must exist, be mounted and have appropriate parent-directory traversal permissions before deployment; Terraform must only create/own the `ubuntu-servers/` pool. Do not aim a pool at the dataset mountpoint or put a backing image inside the environment pool. Keep the base and overlays on the same mounted dataset if desired, but qcow2 backing paths are absolute: never move or overwrite a base while overlays exist. Confirm provider pool-destroy behavior on this host before any later destroy, especially for a nonempty directory. No ZFS dataset, quota, reservation or host permissions are created by this repository.

`cloudinit_disk` generates an ISO outside libvirt; the new root opts in to uploading that ISO into a `libvirt_volume` in its pool and attaches the **pool-owned copy** to each VM. The existing K3s module call defaults to the old behavior and keeps its resource addresses. Generated local ISOs can still use the provider's temporary directory: verify available space and permissions there. Verify live domain XML and both disk paths after deployment.

The two example virtual disks total 40 GiB *virtual* capacity, not 40 GiB of immediate ZFS use. qcow2 overlays are thin-provisioned; guest writes, qcow2 metadata, two image copies during publication, ZFS snapshots and retention can consume the ~49 GiB available rapidly. Before opting into a quota, estimate base-image size, expected guest write growth, snapshots and host needs. One possible **policy to evaluate, not configure here** is to keep at least 10–15 GiB free on `rpool` and cap `rpool/vms` at a smaller budget (for example ~30–35 GiB, if the rest of the host permits); a quota below guest growth requirements will cause guest I/O failures rather than safely resize virtual disks. Monitor `zpool list`, `zfs list`, `df`, `du` and snapshot usage. Never set a quota or reserve space merely because of these examples.

## Operator preflight on the **target** workstation (read-only)

1. Verify proposed mountpoint is unused and not already a directory holding data: `findmnt --mountpoint /var/lib/libvirt/images/labs`, `ls -ld /var/lib/libvirt/images/labs` (a nonexistent path is expected before setup); inspect `zfs list -o name,mountpoint,used,avail`, `zpool list`. Decide whether to use the proposed dataset or a different existing filesystem. The operator, separately, creates the dataset/mountpoint and `base/` and ensures `/var/lib/libvirt/images/labs/ubuntu-servers` does **not** already belong to another pool or data owner. Do not run Terraform against a pre-existing unmanaged pool with the same name.
2. Verify the configured host network, bridge and IPs are free: `virsh -c qemu:///system net-list --all`, `ip -4 route`, `ip -br addr`, `ip link show virbr2`, and check VPN routes. `192.168.124.0/24` must not overlap the default `192.168.122.0/24`, host routes or VPN traffic. Check MAC/domain names with `virsh list --all` and existing libvirt XML. Change `terraform.tfvars` if there is a conflict.
3. Check `getent group libvirt-qemu`, `id`, `virsh -c qemu:///system pool-list --all` and filesystem ownership/traversal (`namei -l` on the published base path and pool parent). Set `pool_group_id` to the **locally resolved** group ID, not a copied value. Do not change global `/var/lib/libvirt/images` permissions. The Terraform pool resource specifies root owner, this group and mode `0770` on its *own* target directory; validate actual libvirt volume permissions separately.
4. Confirm Packer output with `qemu-img info --output=json packer/output-ubuntu2404/<actual-image-filename>` before publishing: format must be qcow2, no backing file and virtual capacity <= the configured guest disks (20 GiB in the example). Ensure the actual image is cloneable and cleaned of build cloud-init/SSH state. Use [Packer publication](../../packer/README.md), and inspect `qemu-img info --backing-chain <overlay>` after a later deployment. Terraform will not build or publish the image.
5. Check AppArmor confinement: `aa-status`, active libvirt/QEMU profiles and libvirt logs. The original host override `etc/apparmor.d/local/abstractions/libvirt-qemu` allows **only** `/var/lib/libvirt/images/lab/`; it does not cover `/var/lib/libvirt/images/labs/base/` or the new pool. The operator must ensure the host's libvirt-generated domain profiles permit reading the published `.qcow2` and writing overlays/`.iso` under the new path, or install a narrowly scoped local policy. Verify access under confinement with an actual test guest later; `terraform validate` cannot check AppArmor or file permissions. Keep traversal rights on every parent directory.
6. Confirm `ssh_public_key_path` exists on the Terraform workstation and matches an available private key for Ansible (`ANSIBLE_PRIVATE_KEY_FILE` or ssh-agent). Ensure the published image path exists, is readable by the libvirt/QEMU runtime, and stays immutable. Check `df -h` on dataset and temporary paths.

The supplied workstation facts (Ubuntu 24.04.5, 16 CPUs, 62 GiB RAM, ZFS `rpool` ~49 GiB free, default NAT only and no custom pools) are operator-reported; these checks must be repeated on the host immediately before deployment. This repository has not run them on that workstation.

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

`env-tf-apply` and `env-tf-destroy` are explicit operator actions; no target runs them automatically. `env-tf-destroy` prompts and refers only to this root's state. The default `make tf-*`, `make up`, and `make ansible-site` still refer to the old K3s root. The new root's local state is `environments/ubuntu-servers/terraform.tfstate`, ignored by Git; protect and back it up outside the checkout. Never copy the original workstation's K3s state to this host.

After the first apply, `make ENV=ubuntu-servers env-state-backup` creates a timestamped local state copy (also ignored by Git); separately keep an off-workstation backup.

After a separately reviewed deployment, `ansible/inventories/ubuntu-servers.py` reads this root's `vm_ips` output. Set `ANSIBLE_PRIVATE_KEY_FILE` or use an ssh-agent, then run `make ENV=ubuntu-servers env-ansible-inventory` and, when intended, `make ENV=ubuntu-servers env-ansible-site`. An offline inventory/syntax check before apply uses the clearly marked **example**, not real outputs:

```sh
export UBUNTU_SERVERS_OUTPUTS_FILE="$PWD/ansible/inventories/ubuntu-servers.outputs.example.json"
make ENV=ubuntu-servers env-ansible-inventory
make ENV=ubuntu-servers env-ansible-syntax
unset UBUNTU_SERVERS_OUTPUTS_FILE
```

`ansible/playbooks/ubuntu-servers.yaml` ensures qemu-guest-agent stays running; it never calls the K3s site. When changing DHCP assignments, update root inputs and re-run inventory from outputs, not from an independently maintained IP list. Output-driven inventory needs applied state; the offline fixture verifies only script format and playbook parsing.

The existing K3s version remains `v1.32.0` in the two K3s inventory group-var files; it is no longer a variable for generic Ubuntu hosts.

## Remaining deployment gates

Operator creates/chooses the mounted dataset and `base/`, checks its free space and policy, publishes and verifies an image, sets filesystem permissions and AppArmor policy for the actual paths, chooses collision-free network/bridge/MACs and confirms provider permissions/ISO upload behavior with a reviewed plan and subsequent smoke test. Neither `terraform validate` nor the checks in this repository confirm that libvirt can boot guests on the proposed ZFS path.
