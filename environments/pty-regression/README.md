# Disposable PTY regression environment

This root is a **prepared, unapplied** disposable environment for validating whether the committed `enable_serial_console = false` / `enable_guest_agent = true` configuration can be created cleanly by the libvirt Terraform provider and then reconcile without a PTY inconsistency.

It is deliberately isolated from the persistent K3s and Ubuntu environments. `bin/operate` accepts only the dedicated `bootstrap`, `cleanup` and partial `recover` operations for this root; generic apply/destroy/configure/snapshot/build/up are refused. No Make target was added.

## Fixed disposable identity

| Item | Value |
| --- | --- |
| Terraform root | `environments/pty-regression/` |
| State | `environments/pty-regression/terraform.tfstate` (must be absent before bootstrap) |
| Pool | `pty-regression` |
| Pool path | `/var/lib/libvirt/images/labs/pty-regression` |
| Network | `pty-regression-net` |
| Bridge | `virbr3` |
| Subnet | `192.168.125.0/24` |
| Gateway / DHCP | `192.168.125.1`; `.100`–`.200` |
| VM | `pty-regression-01` |
| MAC | `52:54:00:cc:00:01` |
| Reserved IP | `192.168.125.10` |
| Base image | `/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2` |
| Expected image SHA-256 | `4d6565fd43a775899b03730e72daca4669f8c71ce57e31482b5520965aef790d` |

The variable validations reject changes to these names, the subnet, the bridge, the VM identity, the pool path and the v1 image filename. The pool resource also verifies the image checksum during plan with `filesha256`.

## Isolation guarantees

- The root has its own local state and does not reference either persistent root.
- The pool path is outside `/var/lib/libvirt/images/labs/base/` and outside the existing `ubuntu-servers` pool.
- The base image is referenced as a read-only qcow2 backing file; Terraform does not own or modify it.
- The network, bridge, subnet, pool, VM name, MAC and IP are reserved for this root only.
- `cloudinit_in_pool = true` uploads the generated cloud-init ISO into this root's own pool.
- `enable_guest_agent = true` and `enable_serial_console = false` are explicit module inputs.
- The guest uses the generic Ubuntu cloud-init template, not the K3s template.

## Read-only preflight

Run this first from the repository root:

```sh
bin/pty-regression-preflight
```

It prints the current libvirt inventory and refuses to continue if the proposed names, bridge, subnet, MAC, pool path or state already exist, or if the published v1 image checksum changed. It does not create or modify anything.

## State-free bootstrap procedure

This root has no state yet. Generic controller apply still requires existing state; a dedicated `bootstrap pty-regression` operation accepts only a fixed, reviewed creation-only saved plan. It keeps the controller's canonical-tool manifest, restricted environment, per-checkout lock and exact interactive authorization. `configure pty-regression` is refused rather than selecting the persistent Ubuntu inventory.

1. Complete the read-only preflight and record its output.
2. Initialize only local provider metadata:

   ```sh
   terraform -chdir=environments/pty-regression init -backend=false -input=false
   terraform -chdir=environments/pty-regression validate
   terraform -chdir=environments/pty-regression fmt -check -recursive
   ```

3. Create a saved creation-only plan:

   ```sh
   terraform -chdir=environments/pty-regression plan -input=false \
     -out=pty-regression.tfplan
   terraform -chdir=environments/pty-regression show -no-color pty-regression.tfplan
   ```

4. Review the plan. It must contain **only** these six creates and no updates or destroys:
   - `libvirt_pool.pty_regression`
   - `libvirt_network.pty_regression`
   - `module.compute.libvirt_volume.vm_disk["pty-regression-01"]`
   - `module.compute.libvirt_cloudinit_disk.commoninit["pty-regression-01"]`
   - `module.compute.libvirt_volume.cloudinit_iso["pty-regression-01"]`
   - `module.compute.libvirt_domain.vm["pty-regression-01"]`

   Confirm the plan does not mention `lab`, `lab-net`, `ubuntu-servers`, `ubuntu-servers-net`, `ubuntu-server-01`, `ubuntu-server-02` or the base image as a managed resource.

5. Have the operator create and review `.local-tools.json` as described in [the controller runbook](../../docs/OPERATION-CONTROLLER.md). It is absent on this host. After it exists, `/usr/bin/python3 -I bin/operate validate-tools pty-regression` checks canonical paths without executing tools.
6. **Stop and request explicit operator approval.** Do not apply the plan as part of preparation.
7. Immediately before an approved bootstrap, repeat `bin/pty-regression-preflight` and inspect the saved plan again. Then invoke:

   ```sh
   /usr/bin/python3 -I bin/operate bootstrap pty-regression
   ```

   Compare `sha256sum environments/pty-regression/pty-regression.tfplan` to the reviewed plan checksum. The controller requires the exact terminal token `bootstrap pty-regression <plan-SHA-256>`, absent state and state artifacts, no conflicting local libvirt resources, exactly six in-scope creates and the reviewed guest-agent/console/image/network settings. It inspects and applies the same sealed plan bytes; a changed plan path cannot substitute different bytes.

8. Record the apply result, state/taint status, domain XML, guest/cloud-init/SSH/guest-agent health, and a refreshed plan. A running VM alone is not a pass.

## Post-create validation

```sh
terraform -chdir=environments/pty-regression state list
terraform -chdir=environments/pty-regression output -json
virsh -c qemu:///system dumpxml pty-regression-01
terraform -chdir=environments/pty-regression plan -input=false
```

Expected checks:

- The domain has the guest-agent channel.
- The domain has no explicit serial console in the committed configuration. If libvirt adds a default console, record exactly what it adds and whether the provider readback remains stable.
- A subsequent plan is clean and the resource is not tainted.
- The base image checksum is unchanged.
- The persistent Ubuntu VMs, pool, network and image are untouched.

Back up the new local state and record the overlay/ISO paths before any cleanup or further experiment.

## Cleanup procedure

Cleanup is a separate destructive operation and requires separate approval.
If bootstrap partially succeeds, the state is tainted or the destroy plan is not exactly six in-scope deletes, stop for state/domain inspection and a new recovery review; do not bypass the cleanup guard.

1. Confirm the experiment is finished and the state/evidence are recorded.
2. Create a destroy plan:

   ```sh
   terraform -chdir=environments/pty-regression plan -destroy -input=false \
     -out=pty-regression-destroy.tfplan
   terraform -chdir=environments/pty-regression show -no-color pty-regression-destroy.tfplan
   ```

3. Review that it destroys only the six disposable resources above. It must not mention persistent pools, networks, domains or the base image.
4. After separate approval, invoke the dedicated cleanup operation:

   ```sh
   /usr/bin/python3 -I bin/operate cleanup pty-regression
   ```

   Compare the destroy-plan checksum to the independently reviewed artifact. The controller requires the exact terminal token `cleanup pty-regression <destroy-plan-SHA-256>`, existing state, exactly six in-scope deletes, matching live domain/pool/network UUIDs and no extra pool volumes or dependent domains. It applies only the sealed, reviewed destroy plan.

5. Verify the disposable pool, network, bridge and domain are gone, the local state is empty, and the persistent environments plus image checksum are unchanged.

Do not use `bin/destroy-vm`, `virsh undefine`, or any Make destroy target for this environment.

If the VM is **absent after a partial apply**, normal UUID-checked cleanup is unavailable. Preserve state/evidence, inspect `terraform state list` and live pool/network UUIDs and volumes, then follow the separately approved, subset-only `recover pty-regression <recovery-plan-SHA-256>` procedure in [the PTY runbook](../../docs/PTY-REGRESSION.md#10-partial-creation-recovery-when-no-vm-exists). If the VM exists without correct state ownership, state is missing/corrupt, or resources differ, stop for a separate restore/import/repair review.

## AppArmor note

Existing Ubuntu domains are confined by libvirt-generated per-domain AppArmor profiles. Those profiles include the exact overlay, base image and cloud-init ISO paths under `/var/lib/libvirt/images/labs/`. The tracked local abstraction only mentions the old `/var/lib/libvirt/images/lab/` path and is not installed at the system local-policy path on this host. Fresh creation is therefore expected to generate a new profile for `pty-regression-01` automatically, but this must be confirmed from the new domain's profile and QEMU label after an approved creation. Do not modify or disable AppArmor.

## Current blockers

- Explicit approval is required before any apply or VM creation.
- No `.local-tools.json` exists, so the controller will fail closed until the operator reviews and supplies the workstation manifest.
- AppArmor profile generation and the PTY readback behavior remain unverified until an approved creation.
- The inactive `clone-test` pool remains untouched pending operator clarification.
