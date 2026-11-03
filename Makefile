override SHELL := /bin/sh
override PACKER_DIR := packer
override TF_DIR := terraform
override ANSIBLE_DIR := ansible

# No concurrent workflows within one Make invocation (including make -j).
.NOTPARALLEL:

.PHONY: packer-init packer-fmt packer-fmt-check packer-validate packer-seed packer-build
.PHONY: tf-init tf-fmt tf-validate tf-plan tf-apply tf-apply-auto tf-destroy tf-destroy-auto
.PHONY: ansible-ping ansible-site
.PHONY: up check ssh-key state-backup snapshot require-env legacy-env
.PHONY: env-info env-tf-init env-tf-fmt-check env-tf-validate env-tf-plan env-tf-apply env-tf-destroy env-state-backup
.PHONY: env-ansible-inventory env-ansible-syntax env-ansible-ping env-ansible-site

# The original targets below continue to operate exclusively on the K3s root.
# New env-* targets select a root explicitly; neither plan nor validation deploys it.
ENV ?= k3s-lab
ifeq ($(ENV),k3s-lab)
override ENV_TF_DIR := terraform
override OPERATE_ENV := k3s-lab
override ENV_INVENTORY := inventories/terraform.py
override ENV_PLAYBOOK := playbooks/site.yaml
override ENV_TMPDIR := /var/lib/libvirt/images/lab/cloudinit
else ifeq ($(ENV),ubuntu-servers)
override ENV_TF_DIR := environments/ubuntu-servers
override OPERATE_ENV := ubuntu-servers
override ENV_INVENTORY := inventories/ubuntu-servers.py
override ENV_PLAYBOOK := playbooks/ubuntu-servers.yaml
override ENV_TMPDIR :=
else
$(error Unsupported ENV=$(ENV); choose k3s-lab or ubuntu-servers)
endif

require-env:
	@test "$(origin ENV)" = "command line" || { echo "Specify ENV=k3s-lab or ENV=ubuntu-servers explicitly" >&2; exit 1; }

legacy-env: require-env
	@test "$(ENV)" = "k3s-lab" || { echo "Legacy target is K3s-only; use env-* for ENV=$(ENV)" >&2; exit 1; }

env-info:
	@echo "Environment: $(ENV) | Terraform root: $(ENV_TF_DIR) | local state: $(ENV_TF_DIR)/terraform.tfstate"

env-tf-init: require-env env-info
	$(if $(ENV_TMPDIR),TMPDIR=$(ENV_TMPDIR)) terraform -chdir=$(ENV_TF_DIR) init

env-tf-fmt-check: require-env env-info
	terraform -chdir=$(ENV_TF_DIR) fmt -check -recursive

env-tf-validate: require-env env-info
	terraform -chdir=$(ENV_TF_DIR) validate

env-tf-plan: require-env env-info
	$(if $(ENV_TMPDIR),TMPDIR=$(ENV_TMPDIR)) terraform -chdir=$(ENV_TF_DIR) plan

env-tf-apply: require-env env-info
	@/usr/bin/python3 -I bin/operate apply $(OPERATE_ENV)

env-tf-destroy: require-env env-info
	@/usr/bin/python3 -I bin/operate destroy $(OPERATE_ENV)

env-state-backup: require-env env-info
	cp $(ENV_TF_DIR)/terraform.tfstate $(ENV_TF_DIR)/terraform.tfstate.backup.$$(date +%Y%m%d-%H%M%S)

env-ansible-inventory: require-env env-info
	cd $(ANSIBLE_DIR) && ansible-inventory -i $(ENV_INVENTORY) --list

env-ansible-syntax: require-env env-info
	cd $(ANSIBLE_DIR) && ANSIBLE_ROLES_PATH=roles ansible-playbook -i $(ENV_INVENTORY) $(ENV_PLAYBOOK) --syntax-check

env-ansible-ping: require-env env-info
	cd $(ANSIBLE_DIR) && ansible all -m ping -i $(ENV_INVENTORY)

env-ansible-site: require-env env-info
	@/usr/bin/python3 -I bin/operate configure $(OPERATE_ENV)

# --- Pre-flight checks ---

check: legacy-env
	@echo "Checking prerequisites..."
	@command -v virsh >/dev/null 2>&1 || { echo "Missing: virsh"; exit 1; }
	@command -v terraform >/dev/null 2>&1 || { echo "Missing: terraform"; exit 1; }
	@command -v ansible-playbook >/dev/null 2>&1 || { echo "Missing: ansible-playbook"; exit 1; }
	@virsh -c qemu:///system pool-info lab >/dev/null 2>&1 || { echo "Missing: libvirt pool 'lab'"; exit 1; }
	@test -f $(TF_DIR)/terraform.tfstate || { echo "Missing: terraform state"; exit 1; }
	@echo "All checks passed."

# --- SSH key (fail early if missing) ---

ssh-key: legacy-env
	@test -f ~/.ssh/id_ed25519.pub || test -f ~/.ssh/id_rsa.pub || { echo "No SSH public key found"; exit 1; }

# --- Packer ---

packer-init:
	cd $(PACKER_DIR) && packer init .

packer-fmt:
	cd $(PACKER_DIR) && packer fmt .

packer-fmt-check:
	cd $(PACKER_DIR) && packer fmt -check .

packer-validate: packer-seed
	cd $(PACKER_DIR) && packer validate .

packer-seed:
	cd $(PACKER_DIR) && ./create-seed.sh

packer-build:
	@/usr/bin/python3 -I bin/operate build ubuntu-servers

# --- Terraform ---

tf-init: legacy-env
	cd $(TF_DIR) && TMPDIR=/var/lib/libvirt/images/lab/cloudinit terraform init

tf-fmt: legacy-env
	cd $(TF_DIR) && terraform fmt

tf-validate: legacy-env
	cd $(TF_DIR) && terraform validate

tf-plan: legacy-env
	cd $(TF_DIR) && TMPDIR=/var/lib/libvirt/images/lab/cloudinit terraform plan

tf-apply: legacy-env
	@/usr/bin/python3 -I bin/operate apply k3s-lab

tf-apply-auto:
	@echo "tf-apply-auto disabled; use an explicitly approved env-tf-apply" >&2; exit 1

tf-destroy: legacy-env
	@/usr/bin/python3 -I bin/operate destroy k3s-lab

tf-destroy-auto:
	@echo "tf-destroy-auto disabled; use an explicitly approved env-tf-destroy" >&2; exit 1

# --- Terraform state backup ---

state-backup: legacy-env
	cp $(TF_DIR)/terraform.tfstate $(TF_DIR)/terraform.tfstate.backup.$$(date +%Y%m%d-%H%M%S)

# --- Ansible ---

ansible-ping: legacy-env
	cd $(ANSIBLE_DIR) && ansible all -m ping -i inventories/terraform.py

ansible-site: legacy-env
	@/usr/bin/python3 -I bin/operate configure k3s-lab

# --- End-to-end ---

up: legacy-env
	@/usr/bin/python3 -I bin/operate up k3s-lab

# --- Snapshots ---

snapshot: require-env env-info
	@test "$(origin VM)" = "command line" || { echo "Specify one VM=<name> explicitly" >&2; exit 1; }
	@/usr/bin/python3 -I bin/operate snapshot $(OPERATE_ENV)
