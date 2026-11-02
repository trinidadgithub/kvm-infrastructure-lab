# Operation controller (Phase 2)

This describes the Phase 2 `bin/operate` + Makefile safety controls. Their commit is **not** an infrastructure deployment approval. [Engineering continuity](ENGINEERING-CONTINUITY.md) is the authoritative handoff.

## Workstation tool manifest

Before using a protected target, create `.local-tools.json` at the repository root, outside Git (`.gitignore` excludes it). Review each absolute tool path and its **current canonical target** on the workstation; do not copy values from another machine or blindly trust `command -v`. The [example manifest](local-tools.example.json) has no credentials and contains **placeholders, not usable workstation paths**:

```json
{
  "executables": {
    "terraform": {"path": "/home/USER/.tfenv/bin/terraform", "resolved": "/home/USER/.tfenv/versions/VERSION/terraform"},
    "virsh": {"path": "/usr/bin/virsh", "resolved": "/usr/bin/virsh"},
    "ansible_playbook": {"path": "/usr/bin/ansible-playbook", "resolved": "/usr/bin/ansible-playbook"},
    "packer": {"path": "/usr/bin/packer", "resolved": "/usr/bin/packer"}
  },
  "k3s_tmpdir": "/var/lib/libvirt/images/lab/cloudinit",
  "k3s_ssh_public_key": "/home/USER/.ssh/id_ed25519.pub"
}
```

**Schema:** `executables` is an object with keys `terraform`, `virsh`, `ansible_playbook`, `packer`; each entry is an object with absolute-string `path` and `resolved` fields. `path` is the operator-selected executable (possibly a tfenv symlink), while `resolved` must equal its canonical, executable file. An operation requires only its own tool entries; the full manifest-validation command below requires all four. `k3s_tmpdir` is an absolute-string path to an **existing** directory for K3s apply/destroy/up; `k3s_ssh_public_key` is an absolute-string path to an existing public key for `up`. Ubuntu does not use the K3s-specific paths. The controller rejects missing or non-executable binaries, relative paths and changed symlink targets. No host directory is created by a denied operation.

**Operator procedure (not performed here):**

1. Inspect the installed tools' actual paths, ownership and versions. On a tfenv host inspect both the `~/.tfenv/bin/terraform` symlink and its canonical versioned target (`readlink -f`); verify the target binary, not merely a PATH lookup. Similarly review the exact `virsh`, `ansible-playbook` and `packer` binaries. Ensure any `k3s_tmpdir` and K3s public key belong to the intended original workstation.
2. Copy `docs/local-tools.example.json` to repository-root `.local-tools.json`, replace every placeholder with locally inspected paths, and restrict access appropriately. This is operator-owned configuration; the controller neither generates nor approves it, and it must remain uncommitted.
3. From the repository root, run **only the read-only validation** `/usr/bin/python3 -I bin/operate validate-tools ubuntu-servers` (or `validate-tools k3s-lab`). It parses the manifest, resolves all four binaries, prints the selected root and canonical paths, and exits without launching any tool, acquiring the operation lock or modifying infrastructure. Confirm the output matches the reviewed paths. It does not inspect libvirt or verify K3s temp/key paths; those are checked by the relevant protected operation before approval.
4. After upgrading Terraform via tfenv or upgrading another tool, re-inspect its binary and symlink target, update `resolved` (and `path` if needed) deliberately, then repeat validation and a separately reviewed infrastructure plan. A symlink-target change without a manifest update fails closed.

**Bootstrap limitation:** apply/destroy are intentionally limited to roots already possessing a local state file. The file-existence check does **not** prove that the state is complete or correct; inspect its addresses and a reviewed plan. To safely add a new environment later, first design a distinct root and state with unique VM/MAC/network/pool names, verify the host-owned base-image checksum and backing paths, check libvirt URI, permissions, capacity and AppArmor, initialize that root, review a creation-only plan and provide a **separate one-time bootstrap approval**. Back up the new state and image/overlay data afterward. No bootstrap command or bypass is implemented in Phase 2. This is a prerequisite for future environment-generation automation.

The controller uses `/usr/bin/python3` on Ubuntu, invokes tools by **absolute canonical paths** and passes a restricted child environment (`PATH=/usr/bin:/bin`, with no inherited `TF_CLI_ARGS*`, `TF_VAR_*`, `TF_WORKSPACE`, `ANSIBLE_CONFIG`, or `PYTHONPATH`). Ansible receives an explicit inventory, playbook and roles path; Packer receives the explicitly supplied absolute `PKR_VAR_ssh_private_key` for its seed and builder. Terraform workstation inputs belong in the selected root's private tfvars. A custom Terraform workspace or environment-based variable override is not supported by these protected targets. `virsh` snapshot checks are scoped to local `qemu:///system`; remote libvirt URI support requires a separate design.

This manifest is **operational configuration, not a security credential or cryptographic trust anchor**. A user able to edit the manifest, repository, installed executables or execution account can defeat local controls. Canonical-path checks detect tfenv symlink changes, not in-place binary replacement. The controller fixes the Terraform root and strips CLI/environment overrides, but does not prove the libvirt provider URI or other values in private tfvars: inspect them and the plan before approval. Stronger enforcement would require a separately permissioned execution identity, trusted immutable executables/configuration and OS-level access controls to libvirt/storage. Other Make targets that merely format, validate or plan are not executed through this controller; review their toolchain and inputs as appropriate.

## Authorized operations

All examples are **commands for a later, separately reviewed operator action**, not commands run during this phase. Make passes a fixed, reviewed environment mapping to `bin/operate`; direct invocations accept only `<operation> <environment>` and snapshot reads `VM` from the environment. It does **not** accept `-- <command>` or shell snippets.

| Request | Required exact terminal token | Resolved action |
| --- | --- | --- |
| `make ENV=ubuntu-servers env-tf-apply` | `apply ubuntu-servers` | Terraform apply in `environments/ubuntu-servers` |
| `make ENV=k3s-lab tf-destroy` | `destroy k3s-lab` | Terraform destroy in `terraform/`; no auto-approve |
| `make ENV=ubuntu-servers env-ansible-site` | `configure ubuntu-servers` | Ubuntu inventory/playbook only |
| `make packer-build` | `build ubuntu-servers` | Generate build seed, then Packer build from `packer/`; no image publication |
| `make ENV=ubuntu-servers VM=ubuntu-server-01 snapshot` | `snapshot ubuntu-servers ubuntu-server-01` | One VM, after name **and UUID** match this root's outputs and local libvirt |
| `make ENV=k3s-lab up` | First `apply k3s-lab`, then `configure k3s-lab` | K3s preflight, Terraform apply, Ansible site in order; no rollback if a later step fails |

The controller prints the resolved root/cwd and command before requesting input, then logs each executed command and its exit status. A directly invoked controller returns the child status (or `128 + signal` for a signaled child); **GNU Make normally returns its own failure status, often `2`, even when the controller printed a child's `42`**. It holds a nonblocking per-checkout lock (`.local-operations.lock`, ignored by Git) across authorization and execution; another controller in the same checkout fails closed rather than running concurrently. The lock is released when the controller returns, fails or exits, but the ignored lock *file* can remain. `.NOTPARALLEL` applies only to one Make process. Two different checkouts and direct Terraform/virsh invocations are **not** serialized by the controller; Terraform's state lock remains necessary. An interrupted command *after* execution begins can leave a partial result and requires inspection, not automatic rollback.

`tf-apply-auto` and `tf-destroy-auto` fail intentionally. Legacy K3s targets require command-line `ENV=k3s-lab`; `ENV=ubuntu-servers` on a legacy target fails instead of redirecting to K3s. Plan review, state/off-host backup and guest-health verification remain separate responsibilities. Never use the persistent Ubuntu or K3s VMs as regression fixtures.

## Stub-only acceptance tests

`python3 -m unittest discover -s tests -p 'test_make_safety.py' -v` copies Make/controller into temporary directories and creates **only stub executables** in those fixtures. It covers refusal/invalid/blank/EOF/SIGINT, positive operations, `MAKE`/`MAKEFLAGS`, `SHELL`, `PATH`, `ANSIBLE_DIR`/`PACKER_DIR` overrides, symlink changes, read-only manifest validation, child status propagation/lock release, direct helper command injection, snapshot membership/UUID mismatches, K3s/Ubuntu scoping, `up` ordering/partial failure and simultaneous Make processes. No real Terraform, libvirt, Packer, Ansible, or guest-configuration command is called. Passing tests validate the local safety contract, **not** provider behavior or host permissions.
