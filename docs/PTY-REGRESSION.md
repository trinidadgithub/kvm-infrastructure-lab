# PTY regression environment: completed normal lifecycle

**Status:** the separately approved bootstrap, no-change reconciliation and independently authorized normal cleanup succeeded on 2026-11-03. The disposable VM, network, bridge, pool and media are **gone**. The PTY Terraform state file remains at serial **14** with **zero managed resources**. Historical plan and operation examples below are evidence, **not** authorization to recreate or delete infrastructure.

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

## Completed initial experiment — independently verified

| Evidence | Result |
| --- | --- |
| Configuration checkpoint | `b99f0255c8ce52017dd7843f57b328499afa0e06` |
| Toolchain | Terraform **1.11.2**, locked `dmacvicar/libvirt` **0.9.9**, provider URI `qemu:///system` |
| Approved saved creation plan | SHA-256 `3842aab121e013eddb983dd2c10a5f87e19d56313013e27dd5ee402080aa9bcb`; six creates, zero changes/destroys |
| Controller bootstrap | Exact digest-bearing approval was supplied to `bin/operate bootstrap pty-regression`; Terraform exited **0**, **6 added, 0 changed, 0 destroyed**; **no provider inconsistency** |
| State and identity | Exactly six expected addresses in `environments/pty-regression/terraform.tfstate`, **no Terraform-tainted instances**; pool/network/domain UUIDs match local libvirt; VM UUID `e33929f5-fe83-477f-9d0d-504ac4ef0836` |
| Serial/agent devices | Terraform state has `consoles = []`; live domain XML has **zero serial and zero console devices**. `org.qemu.guest_agent.0` channel is connected and `guest-ping` responded |
| AppArmor | Generated `libvirt-e33929f5-fe83-477f-9d0d-504ac4ef0836` profile is **enforcing**; overlay `rwk`, v1 backing image `rk`, cloud-init ISO `rk` |
| Storage and image | Read-only `qemu-img info -U --backing-chain` showed the disposable 20 GiB qcow2 overlay backed by `/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2`; image SHA-256 remains `4d6565fd43a775899b03730e72daca4669f8c71ce57e31482b5520965aef790d` |
| Guest and reconciliation | VM running at reserved `192.168.125.10`; SSH works, hostname correct, cloud-init **done** with `errors: []`, guest agent active, guest clock NTP-synchronized; fresh Terraform plan returned detailed exit **0, no changes** |
| Persistent Ubuntu servers | `ubuntu-server-01` UUID `034de61a-fed6-40bf-8c82-cbeb923255d4` and `ubuntu-server-02` UUID `5f4d96cb-b655-4b6f-83e4-877b3fdcef18` remained unchanged |

**Separate diagnostic observations:** cloud-init records `last_update: Thu, 01 Jan 1970 00:00:32 +0000` although the guest's current UTC clock is correct and `NTPSynchronized=yes`. After the explicit read-only `guest-ping`, libvirt `dominfo` reports **`tainted: custom guest agent control commands issued`**. That is a **libvirt domain diagnostic**, not Terraform resource taint: the Terraform state has no tainted instances and the subsequent plan is no-change. Neither observation is a Terraform provider inconsistency.

The local, mode-`0600` evidence logs are `/tmp/opencode/pty-regression-bootstrap-20261103T160143Z-3511188.log` and `/tmp/opencode/pty-regression-reconciliation-20261103T160715Z-3514579.log`. These paths reference host-local evidence only; log contents, state, private tfvars, SSH material and saved plans are **not** committed.

## Completed normal cleanup — independently verified

After a separate review, the saved destroy plan proposed **0 creates, 0 changes and exactly 6 deletes**, limited to the six addresses in §6. Its approved SHA-256 was `be905b9f5903c0aa7038c4dfdd50ca34a86b91551983be3d35c220f5f1dd2c6b`. The controller revalidated the manifest, local state, live UUIDs, pool volumes, dependencies and sealed plan; its independently authorized `cleanup pty-regression` invocation exited **0**. Terraform reported **0 added, 0 changed, 6 destroyed**. No direct `terraform destroy`, retry, untaint, import or partial recovery was used.

**Post-cleanup read-only checks:** the local PTY state file still exists (serial **14**) but `terraform state list` is empty. The disposable domain, NAT network, `virbr3` bridge, libvirt pool, pool directory, overlay, pool-owned cloud-init ISO and provider-generated temporary cloud-init ISO were absent. Both persistent Ubuntu Servers remained running with unchanged UUIDs: `ubuntu-server-01` `034de61a-fed6-40bf-8c82-cbeb923255d4` and `ubuntu-server-02` `5f4d96cb-b655-4b6f-83e4-877b3fdcef18`. Their pool/network identities and volumes, the default network and unrelated inactive/autostart-enabled `clone-test` pool (UUID `b6b3006f-ddbb-435e-b1d6-aa7f5eb25a44`) were preserved. The published v1 image remained at mode `0444`, with SHA-256 `4d6565fd43a775899b03730e72daca4669f8c71ce57e31482b5520965aef790d`.

**Protected host-local evidence (references only; do not commit contents):** cleanup log `/tmp/opencode/pty-regression-cleanup-20261103T181144Z-3591632.log`; pre-cleanup state backup `/tmp/opencode/pty-regression-state-backups/pty-regression-state-before-cleanup-20261103T175816Z-serial7-3582967.tfstate.json`; backup metadata `/tmp/opencode/pty-regression-state-backups/pty-regression-cleanup-evidence-20261103T175816Z.json`; pre-cleanup UUID baseline `/tmp/opencode/pty-regression-state-backups/pty-regression-pre-cleanup-20261103T181122Z-3591314.json`; post-cleanup verification `/tmp/opencode/pty-regression-state-backups/pty-regression-post-cleanup-20261103T181331Z-3592948.json`. The backup/evidence directory is mode `0700` and these files were verified mode `0600`. The operator accepted permanent loss of the disposable overlay; no overlay copy was made.

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

### Verified impact on fresh creation

The approved creation **did** generate an enforcing profile for `pty-regression-01` without changing AppArmor policy. Its generated `.files` fragment grants the new overlay `rwk`, the v1 backing image `rk` and the pool-owned ISO `rk`. The QEMU process reported the matching profile in enforce mode.

During initial creation, the generated profile and QEMU confinement were inspected with read-only checks equivalent to:

```sh
ls -la /etc/apparmor.d/libvirt/libvirt-<new-uuid>*
cat /etc/apparmor.d/libvirt/libvirt-<new-uuid>.files
pgrep -a qemu
cat /proc/<qemu-pid>/attr/current
```

Do not modify or disable AppArmor. If the new profile is missing or denied paths appear in libvirt logs, stop and report before any further operation.

Evidence limitation: unprivileged `aa-status` was denied, so this assessment used the readable generated profile files and `/proc/<pid>/attr/current`, not a privileged AppArmor status dump.

## 4. Pre-bootstrap libvirt and host inventory (historical snapshot)

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

There was no host route for `192.168.125.0/24` **before bootstrap**; the approved network used that subnet on `virbr3` until cleanup removed it.

## 5. Selected collision-free identifiers

| Item | Selected value |
| --- | --- |
| Terraform root | `environments/pty-regression/` |
| State | `environments/pty-regression/terraform.tfstate` (absent before bootstrap; held six resources during the test; now serial 14 with none) |
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

Immediately before bootstrap, `bin/pty-regression-preflight` confirmed:

- state absent
- domain, network, pool and bridge absent
- no route or libvirt network using `192.168.125.0/24`
- no domain using MAC `52:54:00:cc:00:01`
- pool path absent
- v1 image checksum matches
- persistent Ubuntu domains, pool and network are present

## 6. Approved creation plan and resources

The approved saved plan contained exactly six creates; all six were created through the controller:

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

At checkpoint review and immediately before bootstrap, the saved plan's SHA-256 was `3842aab121e013eddb983dd2c10a5f87e19d56313013e27dd5ee402080aa9bcb`. It is retained as historical evidence, **not** authorization to apply it again.

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

## 8. Completed bootstrap procedure (historical; do not rerun)

This **state-free, one-time, controller-gated** procedure was completed with separate operator approval. The following steps record what was reviewed and executed; the VM existed during the experiment, but only its **empty state file** remains. **Do not rerun bootstrap.**

1. `bin/pty-regression-preflight` passed before creation.
2. Local provider metadata was initialized and configuration validated:

   ```sh
   terraform -chdir=environments/pty-regression init -backend=false -input=false
   terraform -chdir=environments/pty-regression validate
   terraform -chdir=environments/pty-regression fmt -check -recursive
   ```

3. The saved creation plan was generated and reviewed:

   ```sh
   terraform -chdir=environments/pty-regression plan -input=false \
     -out=pty-regression.tfplan
   terraform -chdir=environments/pty-regression show -no-color pty-regression.tfplan
   ```

4. The plan contained exactly six creates and no persistent resources.
5. The operator-approved, Git-ignored `.local-tools.json` was created with mode `0600`; `/usr/bin/python3 -I bin/operate validate-tools pty-regression` passed using the reviewed canonical paths.
6. **Explicit operator approval** was obtained for the plan and its SHA-256.
7. Immediately before the approved bootstrap, the read-only preflight and plan digest were rechecked; the controller was invoked once:

   ```sh
   /usr/bin/python3 -I bin/operate bootstrap pty-regression
   ```

   The controller accepted the exact token `bootstrap pty-regression <64-character-plan-SHA-256>` and applied the same sealed bytes it inspected. It returned success with six creates and no provider inconsistency.

8. The apply result, state/taint status, domain XML, AppArmor profile, guest/cloud-init/SSH/guest-agent health and refreshed plan were recorded above.

The initial-creation test passed: clean creation, no Terraform-tainted resource and a subsequent no-change plan, corroborated by guest and live XML checks. This does not establish restart persistence or a working explicit PTY serial console.

## 9. Cleanup procedure

The **separately authorized normal cleanup completed successfully**. The commands below record the reviewed plan and controller operation historically; they are **not** permission to repeat cleanup. If a future experiment partially succeeds, preserve state and inspect it rather than bypassing the cleanup guard.

```sh
terraform -chdir=environments/pty-regression plan -destroy -input=false \
  -out=pty-regression-destroy.tfplan
terraform -chdir=environments/pty-regression show -no-color pty-regression-destroy.tfplan
```

The plan was reviewed as exactly six disposable deletes with SHA-256 `be905b9f5903c0aa7038c4dfdd50ca34a86b91551983be3d35c220f5f1dd2c6b`. After independent operator approval, the controller was invoked once:

```sh
/usr/bin/python3 -I bin/operate cleanup pty-regression
```

The controller required the exact token `cleanup pty-regression <64-character-destroy-plan-SHA-256>`, verified the state, all six deletes, live UUIDs and volumes, and applied only the sealed bytes it inspected. Terraform exited successfully: **0 added, 0 changed, 6 destroyed**.

The disposable resources were verified gone, state was verified empty at serial 14, and persistent Ubuntu resources and the v1 image checksum remained unchanged. Neither `bin/destroy-vm`, `virsh undefine`, nor a Make destroy target was used.

## 10. Partial-creation recovery when no VM exists

**Not exercised during this successful normal lifecycle.** The VM is removed and the state is empty; the following partial-failure path remains a design/tested-with-stubs contingency, **not** a live-validated recovery workflow or standing authorization.

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

## 11. Completed lifecycle checklist

1. **Completed:** reviewed and validated Git-ignored `.local-tools.json`, image/creation-plan checksums, six-create plan and explicit bootstrap approval.
2. **Completed:** state and UUID ownership, no Terraform taint, XML/agent/AppArmor/backing-chain checks, SSH/cloud-init/guest time, unchanged v1 hash and a fresh **no-change** plan. Compare live XML as well as plans because `ignore_changes = [devices]` can conceal drift.
3. **Completed:** operator accepted disposable overlay loss and a protected local state backup (no overlay copy); independent six-delete cleanup plan and digest were reviewed and separately authorized.
4. **Completed:** controller-mediated normal cleanup and post-cleanup verification of empty serial-14 state, absent disposable resources, unchanged persistent Ubuntu/`clone-test` identities and retained v1 image checksum. Partial recovery (§10), VM restart and Ansible configuration were **not** performed.

## 12. Remaining blockers and open questions

1. The normal creation → no-change reconciliation → cleanup lifecycle succeeded for **one disposable console-disabled VM** with this Terraform/provider/host combination. This does **not** prove the original PTY-path provider inconsistency is universally fixed or establish a useful PTY-backed serial-console variant.
2. The shared module still has `ignore_changes = [devices]`, which may conceal future device drift; no restart/persistence test or Ansible configuration was performed on the disposable guest.
3. Partial-failure `recover` was exercised only with stubs; **real partial recovery is untested**. The protected state backup was local; off-host state/overlay restore remains untested.
4. The unrelated `clone-test` pool remains inactive and preserved; its historical ownership/cleanup remains unresolved. K3s deployment status on any other workstation remains unknown.

The empty local PTY state file and ignored saved plans are historical artifacts, not ownership of a live domain, pool or network. Any future disposable experiment needs its own plan, collision review and separate approvals.
