# KVM infrastructure lab

Packer images, Terraform-managed libvirt environments, and Ansible guest configuration on Ubuntu hosts.

## Workflow

1. Packer builds qcow2 base images
2. Terraform provisions libvirt resources
3. Ansible configures guests

## Core commands

The existing `terraform/` root and unprefixed `make tf-*`, `make up`, and `make ansible-site` commands still manage the original K3s lab. They do not select the new environment. Supply `ENV=k3s-lab` explicitly for legacy operational targets; `ENV=ubuntu-servers` is required for Ubuntu `env-*` operations.

- Generic Ubuntu environment: [environments/ubuntu-servers/README.md](environments/ubuntu-servers/README.md)
- Completed PTY regression lifecycle (disposable resources removed; local state empty): [experiment record](docs/PTY-REGRESSION.md); the isolated Terraform configuration remains under `environments/pty-regression/`.
- Current engineering handoff and safety notes: [docs/ENGINEERING-CONTINUITY.md](docs/ENGINEERING-CONTINUITY.md)
- Historical refactor design: [docs/REPOSITORY-REFACTOR-DESIGN.md](docs/REPOSITORY-REFACTOR-DESIGN.md)

For the Ubuntu root, select it explicitly: `make ENV=ubuntu-servers env-info`, `make ENV=ubuntu-servers env-tf-init`, `make ENV=ubuntu-servers env-tf-validate`, and (only after host review) `make ENV=ubuntu-servers env-tf-plan`. New `env-*` commands print the Terraform root and local state path before running. Apply, destroy, guest-configuration and snapshot operations require a terminal and an exact scope-specific confirmation; `*-auto` targets are disabled. The PTY regression root has no Make target: its separately authorized controller bootstrap and normal cleanup both completed; partial recovery remains stub-tested only. Neither building nor publishing a Packer image is part of Terraform initialization.

### Shared image commands

- `make packer-init`
- `make packer-build` (creates a build artifact; does not publish a new golden-image version)

### Legacy K3s commands

**Historical P0 corrected in Phase 2:** older Makefile versions allowed a refused destroy prompt to continue in a later shell, auto-approved K3s apply via `up`, and snapshotted all running VMs. The current controller requires exact approvals and VM ownership checks; see its [safety audit](docs/ENGINEERING-CONTINUITY.md#5-p0-makefile-approval-and-scope-audit-historical-defect-and-fix). A reviewed Git-ignored `.local-tools.json` exists on this workstation; its presence is not authorization for a new operation. Review the plan before any infrastructure action.

- `make ENV=k3s-lab tf-init`
- `make ENV=k3s-lab tf-plan`
- `make ENV=k3s-lab tf-apply` (exact interactive authorization)
- `make ENV=k3s-lab ansible-ping`
- `make ENV=k3s-lab ansible-site` (separate interactive authorization)

## Original workstation notes

- Hypervisor runtime images live under `/var/lib/libvirt/images/lab`
- The K3s pool/image path remains `/var/lib/libvirt/images/lab`; the generic environment has separate ownership and configurable paths.
