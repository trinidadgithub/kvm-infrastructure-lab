# KVM infrastructure lab

Packer images, Terraform-managed libvirt environments, and Ansible guest configuration on Ubuntu hosts.

## Workflow

1. Packer builds qcow2 base images
2. Terraform provisions libvirt resources
3. Ansible configures guests

## Core commands

The existing `terraform/` root and unprefixed `make tf-*`, `make up`, and `make ansible-site` commands still manage the original K3s lab. They do not select the new environment.

- Generic Ubuntu environment: [environments/ubuntu-servers/README.md](environments/ubuntu-servers/README.md)
- Refactor architecture: [docs/REPOSITORY-REFACTOR-DESIGN.md](docs/REPOSITORY-REFACTOR-DESIGN.md)

For the new root, select it explicitly: `make ENV=ubuntu-servers env-info`, `make ENV=ubuntu-servers env-tf-init`, `make ENV=ubuntu-servers env-tf-validate`, and (only after host review) `make ENV=ubuntu-servers env-tf-plan`. New `env-*` commands print the Terraform root and local state path before running. Neither building nor publishing a Packer image is part of Terraform initialization.

### Legacy K3s commands

- `make packer-init`
- `make packer-build`
- `make tf-init`
- `make tf-plan`
- `make tf-apply`
- `make ansible-ping`
- `make ansible-site`

## Original workstation notes

- Hypervisor runtime images live under `/var/lib/libvirt/images/lab`
- The K3s pool/image path remains `/var/lib/libvirt/images/lab`; the generic environment has separate ownership and configurable paths.
