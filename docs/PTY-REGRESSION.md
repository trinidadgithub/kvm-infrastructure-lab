# PTY regression environment: preflight and prepared plan

**Status:** prepared, **not applied**. No VM, pool, network, bridge, state or AppArmor change was made. This document records a read-only assessment plus a saved creation-only Terraform plan for review.

**Date:** 2026-11-03

## 1. Scope

The purpose is to test the committed Ubuntu configuration:

- shared compute module
- `enable_guest_agent = true`
- `enable_serial_console = false`
- pool-owned cloud-init ISO
- published Ubuntu 24.04 v1 image as a read-only backing file

The test environment is intentionally disposable and isolated from:

- the persistent Ubuntu servers and their state
- the K3s root and any K3s resources
- the published image
- the existing `clone-test` pool
- AppArmor policy

## 2. `clone-test` pool investigation

Read-only findings:

| Observation | Result |
| --- | --- |
| Pool name | `clone-test` |
| State | inactive |
| Persistent | yes |
| Autostart | yes |
| Target | `/var/lib/libvirt/images/labs/clone-test` |
| Target directory | **does not exist** |
| Volumes | cannot be listed while the pool is inactive; the pool was not activated |
| Terraform ownership | not present in either Terraform state |
| Repository references | none found |
| Libvirt log filenames | `ubuntu-clone-test.log`, `ubuntu-clone-test-02.log` |
| Stale AppArmor profiles | `libvirt-0e030445-…` and `libvirt-5848d3e9-…`, dated 2026-10-28 |

**Conclusion:** the evidence strongly associates `clone-test` with the earlier disposable clone testing described in the continuity document. Its target directory is already missing, so it appears to be a stale persistent pool definition left after disposable clones were removed. It is **not** part of this regression environment and must not be deleted or modified without separate operator approval.

## 3. AppArmor findings

### Effective confinement

- Both running Ubuntu domains use dynamic, per-domain AppArmor profiles.
- `virsh dumpxml --security-info` reports labels such as `libvirt-034de61a-…` and `libvirt-5f4d96cb-…`.
- The running QEMU processes report:

  ```text
  libvirt-034de61a-fed6-40bf-8c82-cbeb923255d4 (enforce)
  libvirt-5f4d96cb-b655-4b6f-83e4-877b3fdcef18 (enforce)
  ```

- Libvirt-generated `.files` fragments include the exact paths used by each domain:
  - overlay disk: `rwk`
  - published v1 backing image: `rk`
  - cloud-init ISO: `rk`

This is the mechanism that permits `/var/lib/libvirt/images/labs/…` access. It is **not** the tracked local abstraction.

### Discrepancy explanation

- The tracked file `etc/apparmor.d/local/abstractions/libvirt-qemu` only names `/var/lib/libvirt/images/lab/**`.
- That file is not installed at `/etc/apparmor.d/local/abstractions/libvirt-qemu` on this host.
- The effective access comes from libvirt's dynamically generated per-domain profile and its `.files` fragment.

### Expected impact on fresh creation

Fresh creation is **likely** to work without additional AppArmor policy because libvirt should generate a new profile for the new domain UUID containing the new overlay, base-image and ISO paths. This cannot be proven without an approved creation.

After an approved creation, verify:

```sh
ls -la /etc/apparmor.d/libvirt/libvirt-<new-uuid>*
cat /etc/apparmor.d/libvirt/libvirt-<new-uuid>.files
pgrep -a qemu
cat /proc/<qemu-pid>/attr/current
```

Do not modify or disable AppArmor. If the new profile is missing or denied paths appear in libvirt logs, stop and report before any further operation.

Evidence limitation: unprivileged `aa-status` was denied, so this assessment used the readable generated profile files and `/proc/<pid>/attr/current`, not a privileged AppArmor status dump.

## 4. Existing libvirt and host inventory

### Domains

| Domain | State | MAC | Network |
| --- | --- | --- | --- |
| `ubuntu-server-01` | running | `52:54:00:bb:00:01` | `ubuntu-servers-net` |
| `ubuntu-server-02` | running | `52:54:00:bb:00:02` | `ubuntu-servers-net` |

No K3s domains exist on this host.

### Networks

| Network | State | Bridge | Subnet |
| --- | --- | --- | --- |
| `default` | active | `virbr0` | `192.168.122.0/24` |
| `ubuntu-servers-net` | active | `virbr2` | `192.168.124.0/24` |

No `lab-net` exists on this host.

### Pools

| Pool | State | Path |
| --- | --- | --- |
| `clone-test` | inactive | `/var/lib/libvirt/images/labs/clone-test` (missing) |
| `ubuntu-servers` | active | `/var/lib/libvirt/images/labs/ubuntu-servers` |

### Bridges and routes

Existing bridge-like interfaces include `virbr0` (down), `virbr2` (up), `docker0`, `br-9f2f0cf0da48`, `br-a1c950626d6f`, `cni0`, `flannel.1`, several `veth*`, and `vnet0`/`vnet1`.

Host routes include:

```text
10.0.7.0/24
10.42.0.0/24
172.17.0.0/16
172.100.0.0/24
192.168.49.0/24
192.168.122.0/24
192.168.124.0/24
```

There is no host route for `192.168.125.0/24`.

## 5. Selected collision-free identifiers

| Item | Selected value |
| --- | --- |
| Terraform root | `environments/pty-regression/` |
| State | `environments/pty-regression/terraform.tfstate` (absent) |
| Pool | `pty-regression` |
| Pool path | `/var/lib/libvirt/images/labs/pty-regression` |
| Network | `pty-regression-net` |
| Bridge | `virbr3` |
| Subnet | `192.168.125.0/24` |
| Gateway | `192.168.125.1` |
| DHCP range | `192.168.125.100`–`192.168.125.200` |
| VM | `pty-regression-01` |
| MAC | `52:54:00:cc:00:01` |
| Reserved IP | `192.168.125.10` |
| Base image | `/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2` |
| Expected SHA-256 | `4d6565fd43a775899b03730e72daca4669f8c71ce57e31482b5520965aef790d` |

`bin/pty-regression-preflight` confirmed:

- state absent
- domain, network, pool and bridge absent
- no route or libvirt network using `192.168.125.0/24`
- no domain using MAC `52:54:00:cc:00:01`
- pool path absent
- v1 image checksum matches
- persistent Ubuntu domains, pool and network are present

## 6. Proposed Terraform resources

The saved plan contains exactly six creates:

| Address | Action | Purpose |
| --- | --- | --- |
| `libvirt_pool.pty_regression` | create | dedicated `dir` pool under `/var/lib/libvirt/images/labs/pty-regression` |
| `libvirt_network.pty_regression` | create | dedicated NAT network `pty-regression-net` on `virbr3` |
| `module.compute.libvirt_volume.vm_disk["pty-regression-01"]` | create | 20 GiB qcow2 overlay backed by the v1 image |
| `module.compute.libvirt_cloudinit_disk.commoninit["pty-regression-01"]` | create | per-VM cloud-init data |
| `module.compute.libvirt_volume.cloudinit_iso["pty-regression-01"]` | create | pool-owned cloud-init ISO |
| `module.compute.libvirt_domain.vm["pty-regression-01"]` | create | 2 vCPU / 2048 MiB disposable domain |

Plan summary:

```text
Plan: 6 to add, 0 to change, 0 to destroy.
```

Key planned domain attributes:

- guest-agent channel: `org.qemu.guest_agent.0`
- `consoles = []`
- MAC `52:54:00:cc:00:01`
- network `pty-regression-net`
- memory `2048` MiB
- vCPU `2`
- q35/KVM domain
- overlay capacity `21474836480` bytes (20 GiB)
- backing image: `/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2`

The plan does not mention any persistent K3s or Ubuntu resource, and the only reference to the base image is the read-only backing path. The saved binary plan is:

```text
environments/pty-regression/pty-regression.tfplan
```

It is Git-ignored. Review it with:

```sh
terraform -chdir=environments/pty-regression show -no-color pty-regression.tfplan
```

At checkpoint review, the regenerated saved plan's SHA-256 was `3842aab121e013eddb983dd2c10a5f87e19d56313013e27dd5ee402080aa9bcb`. This identifies the reviewed local artifact, not an authorization to apply; regenerate and re-review it if any input changes.

## 7. Safety design

- The root has its own local state and no backend shared with another root.
- Variable validation fixes the disposable names, pool path, bridge, subnet, VM identity, MAC, IP and v1 image filename.
- The pool resource verifies `filesha256(base_image)` against the expected v1 checksum during plan.
- A pool precondition rejects a base image inside the disposable pool.
- The shared compute module is reused unchanged.
- The guest-agent channel is enabled and the explicit serial console is disabled at the module call site.
- No Make target was added. `bin/operate` maps `pty-regression` only to `bootstrap`, `cleanup` and partial `recover`; generic apply/destroy/configure/snapshot/build/up are refused. It cannot select the persistent Ubuntu inventory.
- Bootstrap refuses any local state artifact or backend metadata, checks the local libvirt domain/network/pool inventory for conflicts twice, and inspects the fixed saved plan as exactly six creates from empty prior state. It validates the provider configuration, `qemu:///system`, image, identities, guest-agent channel and `consoles = []`.
- Normal cleanup requires existing state, exactly six state-owned deletes, matching live domain/pool/network UUIDs and no extra pool volumes or dependent domains. Partial recovery is a separate operation limited to a state-owned subset **without a live disposable VM**.
- Each operation inspects and executes the **same sealed in-memory plan bytes**; the exact interactive token includes their SHA-256. A changed pathname after review cannot substitute other bytes. The canonical-tool manifest, restricted environment and per-checkout lock still apply. Direct Terraform/libvirt invocations and a different checkout are outside this operational control; host routes and unmanaged directory collisions still require the separate read-only preflight.

## 8. Bootstrap procedure

This is a **state-free, one-time, controller-gated** procedure. It requires separate operator approval before the apply step.

1. Run `bin/pty-regression-preflight`.
2. Initialize and validate local provider metadata:

   ```sh
   terraform -chdir=environments/pty-regression init -backend=false -input=false
   terraform -chdir=environments/pty-regression validate
   terraform -chdir=environments/pty-regression fmt -check -recursive
   ```

3. Recreate or inspect the saved creation plan:

   ```sh
   terraform -chdir=environments/pty-regression plan -input=false \
     -out=pty-regression.tfplan
   terraform -chdir=environments/pty-regression show -no-color pty-regression.tfplan
   ```

4. Confirm the plan is exactly six creates and contains no persistent resources.
5. The operator must create and review `.local-tools.json` as described in [the controller runbook](OPERATION-CONTROLLER.md). It is currently absent. After it exists, `/usr/bin/python3 -I bin/operate validate-tools pty-regression` checks canonical paths without running tools.
6. **Stop and obtain explicit approval.** Do not apply during preparation.
7. Immediately before an approved bootstrap, repeat `bin/pty-regression-preflight`, inspect the saved plan again, then invoke:

   ```sh
   /usr/bin/python3 -I bin/operate bootstrap pty-regression
   ```

   Compare `sha256sum environments/pty-regression/pty-regression.tfplan` with the reviewed digest. The controller requires the exact terminal token `bootstrap pty-regression <64-character-plan-SHA-256>`, verifies the saved plan and then applies the sealed bytes it inspected. A changed plan requires renewed review and approval.

8. Record the apply result, state/taint status, domain XML, AppArmor profile, guest/cloud-init/SSH/guest-agent health, and a refreshed plan.

A successful boot alone is not a pass. The test passes only if initial creation is clean, the domain is not tainted, and a subsequent plan reconciles without a PTY inconsistency.

## 9. Cleanup procedure

Cleanup is separately destructive and requires separate approval.
If creation partially succeeds, state is tainted or the destroy plan is not exactly six in-scope deletes, stop for state/domain inspection and a new recovery review; do not bypass the cleanup guard.

```sh
terraform -chdir=environments/pty-regression plan -destroy -input=false \
  -out=pty-regression-destroy.tfplan
terraform -chdir=environments/pty-regression show -no-color pty-regression-destroy.tfplan
```

Review that only the six disposable resources are destroyed. Then, after separate approval:

```sh
/usr/bin/python3 -I bin/operate cleanup pty-regression
```

Compare the new destroy-plan checksum with the reviewed artifact. The controller requires the exact terminal token `cleanup pty-regression <64-character-destroy-plan-SHA-256>`, verifies state, all six deletes, live UUIDs and pool volumes, then applies only the sealed bytes it inspected.

Verify the disposable resources are gone, the local state is empty, and the persistent Ubuntu/K3s resources and v1 image checksum are unchanged. Do not use `bin/destroy-vm`, `virsh undefine`, or any Make destroy target for this environment.

## 10. Partial-creation recovery when no VM exists

If domain creation fails after pool/network/storage creation, **stop**. An apply failure can leave a valid partial state and live disposable resources; a failed VM need not have a UUID. Do not repeat bootstrap, use normal cleanup, untaint, remove state addresses or directly undefine resources to suppress the error.

1. Freeze writers and preserve the failed apply output, local state, plan and disks. Read **only** the disposable root's addresses with `terraform -chdir=environments/pty-regression state list`; inspect taint/status privately without printing state or keys into shared logs. Compare `virsh -c qemu:///system list --all`, `pool-dumpxml pty-regression`, `net-dumpxml pty-regression-net`, and `vol-list --pool pty-regression` to state ownership. Verify that `pty-regression-01` is truly absent, that pool/network UUIDs match state, no other domain uses their network/storage, and the published image checksum remains unchanged.
2. If state is missing/corrupt, a domain exists without correct state ownership, UUIDs differ, or extra volumes/dependencies exist, **stop for separate restore/import/repair review**. The recovery controller refuses these cases. Do not initialize empty state against live resources.
3. If the VM is absent and state contains only the known disposable subset, create a **separate** saved partial destroy plan:

   ```sh
   terraform -chdir=environments/pty-regression plan -destroy -input=false \
     -out=pty-regression-recovery.tfplan
   terraform -chdir=environments/pty-regression show -no-color pty-regression-recovery.tfplan
   ```

   Review that every action is a delete of exactly the remaining state-owned disposable resources, with no domain or persistent resource. Preserve a protected state/overlay backup first.
4. Obtain **independent recovery approval**, verify `sha256sum environments/pty-regression/pty-regression-recovery.tfplan`, then invoke `/usr/bin/python3 -I bin/operate recover pty-regression` and enter `recover pty-regression <64-character-recovery-plan-SHA-256>`. The controller compares current state addresses to the plan, requires the VM absent, checks live pool/network UUIDs and exact pool volumes, and applies only the sealed reviewed plan. If any check fails, return to step 2.
5. Verify disposable resources and state are gone, then recheck the persistent Ubuntu domains/network/pool and the v1 image checksum. Keep the failure evidence and backups until the recovery review is closed.

This partial recovery was exercised **only with isolated stubs**, not on the host.

## 11. Concise operator checklist

1. Create Git-ignored `.local-tools.json` from `docs/local-tools.example.json`; inspect absolute paths, executable ownership, tfenv's canonical target and versions. Run `/usr/bin/python3 -I bin/operate validate-tools pty-regression` and compare its output to reviewed paths.
2. Re-run `bin/pty-regression-preflight`; confirm absent state/conflicts, correct `qemu:///system`, host routes/bridge/pool path, and `sha256sum /var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2` equals `4d6565fd43a775899b03730e72daca4669f8c71ce57e31482b5520965aef790d`.
3. Review `terraform -chdir=environments/pty-regression show -no-color pty-regression.tfplan`: exactly six creates, zero changes/deletes, `consoles = []`, guest-agent channel, fixed identities and backing path. Verify `sha256sum environments/pty-regression/pty-regression.tfplan` against the reviewed digest. Regenerate/re-review if inputs or the plan changed.
4. Obtain explicit **creation** approval for that plan and its digest; only then use the controller's `bootstrap` operation and enter its full digest-bearing token.
5. Inspect apply result, state/taint, domain UUID/XML, generated AppArmor profile, overlay backing chain, guest/cloud-init/SSH/agent health and published-image checksum. A running guest alone is not success.
6. Review a fresh subsequent plan for **no changes** and compare live device XML because `ignore_changes = [devices]` may conceal drift. Stop on taint or partial failure and use §10.
7. For normal cleanup, make a protected state/overlay backup, review the independent six-delete `pty-regression-destroy.tfplan`, verify its checksum and obtain separate **cleanup** approval. Use the controller's `cleanup` operation with its full digest-bearing token; partial state requires §10 instead.
8. Confirm the disposable domain, network, bridge, pool/volumes and state are gone; recheck both persistent Ubuntu resources and the unchanged v1 checksum. Retain evidence until recovery is verified.

## 12. Remaining blockers and open questions

1. **Explicit approval is required** before any apply, VM creation, restart or cleanup.
2. **PTY behavior on initial creation is still unverified.** The saved plan correctly shows `consoles = []`, but libvirt may add a default console and the provider readback behavior is the subject of the test.
3. **AppArmor profile generation is unverified until creation.** Current evidence suggests dynamic profiles will include the new paths, but this must be checked after an approved apply.
4. **No `.local-tools.json` exists.** The controller fails closed until the operator supplies and reviews the workstation manifest. The PTY mapping is limited to bootstrap/cleanup/recover; `configure` cannot target the persistent Ubuntu inventory.
5. **`clone-test` remains unresolved.** It is not part of this root and must not be deleted or activated without operator direction.
6. **No off-host state/overlay backup exists for this new root yet.** After creation, capture the new state and record overlay/ISO paths before any further experiment.
7. The saved plan must be regenerated if any configuration, provider lock or input changes before approval.
8. Applying a sealed memfd with the real Terraform CLI has **not** been exercised; real `terraform show -json` accepted the sealed creation plan read-only, and apply behavior is covered only by stub tests.
