PACKER_DIR=packer
TF_DIR=terraform
ANSIBLE_DIR=ansible

.PHONY: packer-init packer-fmt packer-fmt-check packer-validate packer-seed packer-build
.PHONY: tf-init tf-fmt tf-validate tf-plan tf-apply tf-apply-auto tf-destroy tf-destroy-auto
.PHONY: ansible-ping ansible-site
.PHONY: up check ssh-key state-backup snapshot
.PHONY: env-info env-tf-init env-tf-fmt-check env-tf-validate env-tf-plan env-tf-apply env-tf-destroy env-state-backup
.PHONY: env-ansible-inventory env-ansible-syntax env-ansible-ping env-ansible-site

# The original targets below continue to operate exclusively on the K3s root.
# New env-* targets select a root explicitly; neither plan nor validation deploys it.
ENV ?= k3s-lab
ifeq ($(ENV),k3s-lab)
ENV_TF_DIR := terraform
ENV_INVENTORY := inventories/terraform.py
ENV_PLAYBOOK := playbooks/site.yaml
ENV_TMPDIR := /var/lib/libvirt/images/lab/cloudinit
else ifeq ($(ENV),ubuntu-servers)
ENV_TF_DIR := environments/ubuntu-servers
ENV_INVENTORY := inventories/ubuntu-servers.py
ENV_PLAYBOOK := playbooks/ubuntu-servers.yaml
ENV_TMPDIR :=
else
$(error Unsupported ENV=$(ENV); choose k3s-lab or ubuntu-servers)
endif

env-info:
	@echo "Environment: $(ENV) | Terraform root: $(ENV_TF_DIR) | local state: $(ENV_TF_DIR)/terraform.tfstate"

env-tf-init: env-info
	$(if $(ENV_TMPDIR),mkdir -p $(ENV_TMPDIR))
	$(if $(ENV_TMPDIR),TMPDIR=$(ENV_TMPDIR)) terraform -chdir=$(ENV_TF_DIR) init

env-tf-fmt-check: env-info
	terraform -chdir=$(ENV_TF_DIR) fmt -check -recursive

env-tf-validate: env-info
	terraform -chdir=$(ENV_TF_DIR) validate

env-tf-plan: env-info
	$(if $(ENV_TMPDIR),mkdir -p $(ENV_TMPDIR))
	$(if $(ENV_TMPDIR),TMPDIR=$(ENV_TMPDIR)) terraform -chdir=$(ENV_TF_DIR) plan

env-tf-apply: env-info
	$(if $(ENV_TMPDIR),mkdir -p $(ENV_TMPDIR))
	$(if $(ENV_TMPDIR),TMPDIR=$(ENV_TMPDIR)) terraform -chdir=$(ENV_TF_DIR) apply

env-tf-destroy: env-info
	@read -r -p "Destroy resources in $(ENV_TF_DIR)/terraform.tfstate? [y/N] " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then echo "Aborted."; exit 0; fi; \
	$(if $(ENV_TMPDIR),mkdir -p $(ENV_TMPDIR) &&) \
	$(if $(ENV_TMPDIR),TMPDIR=$(ENV_TMPDIR)) terraform -chdir=$(ENV_TF_DIR) destroy

env-state-backup: env-info
	cp $(ENV_TF_DIR)/terraform.tfstate $(ENV_TF_DIR)/terraform.tfstate.backup.$$(date +%Y%m%d-%H%M%S)

env-ansible-inventory: env-info
	cd $(ANSIBLE_DIR) && ansible-inventory -i $(ENV_INVENTORY) --list

env-ansible-syntax: env-info
	cd $(ANSIBLE_DIR) && ANSIBLE_ROLES_PATH=roles ansible-playbook -i $(ENV_INVENTORY) $(ENV_PLAYBOOK) --syntax-check

env-ansible-ping: env-info
	cd $(ANSIBLE_DIR) && ansible all -m ping -i $(ENV_INVENTORY)

env-ansible-site: env-info
	cd $(ANSIBLE_DIR) && ANSIBLE_ROLES_PATH=roles ansible-playbook -i $(ENV_INVENTORY) $(ENV_PLAYBOOK)

# --- Pre-flight checks ---

check:
	@echo "Checking prerequisites..."
	@command -v virsh >/dev/null 2>&1 || { echo "Missing: virsh"; exit 1; }
	@command -v terraform >/dev/null 2>&1 || { echo "Missing: terraform"; exit 1; }
	@command -v ansible-playbook >/dev/null 2>&1 || { echo "Missing: ansible-playbook"; exit 1; }
	@virsh pool-info lab >/dev/null 2>&1 || { echo "Missing: libvirt pool 'lab'"; exit 1; }
	@test -f $(TF_DIR)/terraform.tfstate || { echo "Missing: terraform state"; exit 1; }
	@echo "All checks passed."

# --- SSH key (fail early if missing) ---

ssh-key:
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

packer-build: packer-seed
	cd $(PACKER_DIR) && packer build .

# --- Terraform ---

tf-init:
	mkdir -p /var/lib/libvirt/images/lab/cloudinit
	cd $(TF_DIR) && TMPDIR=/var/lib/libvirt/images/lab/cloudinit terraform init

tf-fmt:
	cd $(TF_DIR) && terraform fmt

tf-validate:
	cd $(TF_DIR) && terraform validate

tf-plan:
	mkdir -p /var/lib/libvirt/images/lab/cloudinit
	cd $(TF_DIR) && TMPDIR=/var/lib/libvirt/images/lab/cloudinit terraform plan

tf-apply:
	mkdir -p /var/lib/libvirt/images/lab/cloudinit
	cd $(TF_DIR) && TMPDIR=/var/lib/libvirt/images/lab/cloudinit terraform apply

tf-apply-auto:
	mkdir -p /var/lib/libvirt/images/lab/cloudinit
	cd $(TF_DIR) && TMPDIR=/var/lib/libvirt/images/lab/cloudinit terraform apply -auto-approve

tf-destroy:
	@echo "WARNING: This will destroy ALL lab VMs and volumes!"
	@read -r -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then echo "Aborted."; exit 0; fi
	mkdir -p /var/lib/libvirt/images/lab/cloudinit
	cd $(TF_DIR) && TMPDIR=/var/lib/libvirt/images/lab/cloudinit terraform destroy

tf-destroy-auto:
	@echo "WARNING: This will destroy ALL lab VMs and volumes!"
	@read -r -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then echo "Aborted."; exit 0; fi
	mkdir -p /var/lib/libvirt/images/lab/cloudinit
	cd $(TF_DIR) && TMPDIR=/var/lib/libvirt/images/lab/cloudinit terraform destroy -auto-approve

# --- Terraform state backup ---

state-backup:
	cp $(TF_DIR)/terraform.tfstate $(TF_DIR)/terraform.tfstate.backup.$$(date +%Y%m%d-%H%M%S)

# --- Ansible ---

ansible-ping:
	cd $(ANSIBLE_DIR) && ansible all -m ping -i inventories/terraform.py

ansible-site:
	cd $(ANSIBLE_DIR) && ANSIBLE_ROLES_PATH=roles ansible-playbook -i inventories/terraform.py playbooks/site.yaml

# --- End-to-end ---

up: check ssh-key tf-apply-auto ansible-site
	@echo "Lab is up."

# --- Snapshots ---

snapshot:
	@for vm in $$(virsh list --name --state-running); do \
		echo "Creating snapshot of $$vm..."; \
		virsh snapshot-create-as "$$vm" "snap-$$(date +%Y%m%d-%H%M%S)" --atomic; \
	done
	@echo "Snapshots done."
