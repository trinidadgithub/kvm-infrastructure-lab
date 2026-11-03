# Operation controller (Phase 2 and disposable PTY lifecycle)

This describes the Phase 2 `bin/operate` + Makefile safety controls and the later disposable PTY bootstrap/cleanup/recovery mapping. Code or documentation is **not** an infrastructure deployment approval. [Engineering continuity](ENGINEERING-CONTINUITY.md) is the authoritative handoff.

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

**Operator tool-review procedure:** completed for the PTY lifecycle on this workstation; repeat after tool changes or for another host.

1. Inspect installed tools' actual paths, ownership and versions. A tfenv shim may be a script rather than a symlink: on this workstation `~/.tfenv/bin/terraform` is a wrapper, while the reviewed manifest selects `/home/tmarroquin/.tfenv/versions/1.11.2/terraform` directly. Verify the binary, not merely a PATH lookup. Similarly review `virsh`, `ansible-playbook` and `packer`; K3s-specific paths require separate host review.
2. Copy `docs/local-tools.example.json` to repository-root `.local-tools.json`, replace every placeholder with locally inspected paths, and restrict access appropriately. This is operator-owned configuration; the controller neither generates nor approves it, and it must remain uncommitted.
3. From the repository root, run **only the read-only validation** `/usr/bin/python3 -I bin/operate validate-tools ubuntu-servers` (or `validate-tools k3s-lab` / `validate-tools pty-regression`). It parses the manifest, resolves all four binaries, prints the selected root and canonical paths, and exits without launching any tool, acquiring the operation lock or modifying infrastructure. Confirm the output matches the reviewed paths. It does not inspect libvirt or verify K3s temp/key paths; those are checked by the relevant protected operation before approval.
4. After upgrading Terraform via tfenv or upgrading another tool, re-inspect its binary and symlink target, update `resolved` (and `path` if needed) deliberately, then repeat validation and a separately reviewed infrastructure plan. A symlink-target change without a manifest update fails closed.

**Bootstrap limitation and narrow exception:** generic apply/destroy remain limited to roots already possessing a local state file. The `pty-regression` root has a dedicated `bootstrap` that requires **no state artifacts or backend metadata**, no conflicting local libvirt resources, and exactly six creates from an empty prior state. Normal `cleanup` requires all six state-owned resources, six deletes, matching live domain/pool/network UUIDs and exact pool volumes. Both were separately authorized and completed successfully on the disposable environment; its state file now contains **zero** managed resources, so neither operation is authorized to repeat. A separate `recover` accepts only a reviewed state-owned delete subset when the VM is absent; it refuses missing/corrupt state, an orphan domain or mismatched live objects. **Partial recovery has not run against real infrastructure.** See the [completed PTY lifecycle](PTY-REGRESSION.md). No general state-free bootstrap exists for other environments.

The controller uses `/usr/bin/python3` on Ubuntu, invokes tools by **absolute canonical paths** and passes a restricted child environment (`PATH=/usr/bin:/bin`, with no inherited `TF_CLI_ARGS*`, `TF_VAR_*`, `TF_WORKSPACE`, `ANSIBLE_CONFIG`, or `PYTHONPATH`). Ansible receives an explicit inventory, playbook and roles path; Packer receives the explicitly supplied absolute `PKR_VAR_ssh_private_key` for its seed and builder. Terraform workstation inputs belong in the selected root's private tfvars. A custom Terraform workspace or environment-based variable override is not supported by these protected targets. `virsh` snapshot and PTY cleanup UUID checks are scoped to local `qemu:///system`; remote libvirt URI support requires a separate design.

This manifest is **operational configuration, not a security credential or cryptographic trust anchor**. A user able to edit the manifest, repository, installed executables or execution account can defeat local controls. Canonical-path checks detect tfenv symlink changes, not in-place binary replacement. The controller fixes the Terraform root and strips CLI/environment overrides; generic operations do not prove the libvirt provider URI or other values in private tfvars. The PTY saved-plan guard checks its planned URI and fixed values, but still requires independent plan and live-host review. Stronger enforcement would require a separately permissioned execution identity, trusted immutable executables/configuration and OS-level access controls to libvirt/storage. Other Make targets that merely format, validate or plan are not executed through this controller; review their toolchain and inputs as appropriate.

## Authorized operations

The table documents fixed mappings and required tokens, **not standing authorization**. The PTY bootstrap and normal cleanup were executed once under separate approvals; `recover` remains untested on live infrastructure. Make passes a fixed environment mapping to `bin/operate`; direct invocations accept only `<operation> <environment>` and snapshot reads `VM` from the environment. It does **not** accept `-- <command>` or shell snippets.

| Request | Required exact terminal token | Resolved action |
| --- | --- | --- |
| `make ENV=ubuntu-servers env-tf-apply` | `apply ubuntu-servers` | Terraform apply in `environments/ubuntu-servers` |
| `make ENV=k3s-lab tf-destroy` | `destroy k3s-lab` | Terraform destroy in `terraform/`; no auto-approve |
| `make ENV=ubuntu-servers env-ansible-site` | `configure ubuntu-servers` | Ubuntu inventory/playbook only |
| `make packer-build` | `build ubuntu-servers` | Generate build seed, then Packer build from `packer/`; no image publication |
| `make ENV=ubuntu-servers VM=ubuntu-server-01 snapshot` | `snapshot ubuntu-servers ubuntu-server-01` | One VM, after name **and UUID** match this root's outputs and local libvirt |
| `make ENV=k3s-lab up` | First `apply k3s-lab`, then `configure k3s-lab` | K3s preflight, Terraform apply, Ansible site in order; no rollback if a later step fails |
| `/usr/bin/python3 -I bin/operate bootstrap pty-regression` | `bootstrap pty-regression <plan-SHA-256>` | State-free, fixed six-create saved plan; no Make target |
| `/usr/bin/python3 -I bin/operate cleanup pty-regression` | `cleanup pty-regression <destroy-plan-SHA-256>` | Existing state, independent six-delete plan and matching live ownership; no Make target |
| `/usr/bin/python3 -I bin/operate recover pty-regression` | `recover pty-regression <recovery-plan-SHA-256>` | Separate partial-state destroy plan, no live VM and exact state/live ownership checks; no Make target |

The controller prints the resolved root/cwd and command before requesting input, then logs each executed command and its exit status. For PTY lifecycle operations it reads the fixed saved plan once into a Linux sealed memfd, asks for the **full SHA-256 in the exact token**, rechecks the original path, state and live ownership, then passes the **same sealed descriptor** to Terraform `apply`; pathname substitution cannot change the executed bytes. Real sealed-plan bootstrap and normal cleanup succeeded: **6 created**, subsequent plan **no changes**, then **0 added, 0 changed, 6 destroyed** using reviewed destroy-plan SHA-256 `be905b9f5903c0aa7038c4dfdd50ca34a86b91551983be3d35c220f5f1dd2c6b`. The local state file remains at serial **14** with zero managed resources. This verifies one normal lifecycle, not partial recovery or a universal provider fix. A directly invoked controller returns the child status (or `128 + signal` for a signaled child); **GNU Make normally returns its own failure status, often `2`, even when the controller printed a child's `42`**. It holds a nonblocking per-checkout lock (`.local-operations.lock`, ignored by Git) across authorization and execution; another controller in the same checkout fails closed rather than running concurrently. The lock is released when the controller returns, fails or exits, but the ignored lock *file* can remain. `.NOTPARALLEL` applies only to one Make process. Two different checkouts and direct Terraform/virsh invocations are **not** serialized by the controller; Terraform's state lock remains necessary. An interrupted command *after* execution begins can leave a partial result and requires inspection, not automatic rollback.

`tf-apply-auto` and `tf-destroy-auto` fail intentionally. Legacy K3s targets require command-line `ENV=k3s-lab`; `ENV=ubuntu-servers` on a legacy target fails instead of redirecting to K3s. The `pty-regression` mapping rejects generic apply/destroy/configure/snapshot/build/up, so it cannot accidentally select the persistent Ubuntu inventory. Plan review, host bridge/route and unmanaged-path preflight, state/off-host backup and guest-health verification remain separate responsibilities. Never use persistent Ubuntu or K3s VMs as regression fixtures.

## Stub-only acceptance tests

`python3 -m unittest discover -s tests -p 'test_*.py' -v` runs the original Make/controller tests plus PTY-root invariants and stub-only lifecycle tests. They cover refusal/EOF/SIGINT, prior authorization boundaries and overrides, exact plan scope/actions/provider URI, state artifacts, libvirt conflicts, sealed-byte substitution and digest tokens, full cleanup ownership, partial failure and separately authorized recovery. No real Terraform apply/destroy, libvirt mutation, Packer build, Ansible play or guest configuration is called. Passing tests validate the local safety contract, **not** provider behavior or host permissions.
