packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = "= 1.1.7"
    }
  }
}

locals {
  seed_iso = abspath("${path.root}/seed.iso")
}

source "qemu" "ubuntu2404" {
  iso_url          = var.base_image_url
  iso_checksum     = var.base_image_checksum
  disk_image       = true
  use_backing_file = false

  output_directory = "output-ubuntu2404"
  format           = "qcow2"
  accelerator      = "kvm"
  headless         = true
  vm_name          = "ubuntu-24.04-lab-base.qcow2"

  ssh_username         = "ubuntu"
  ssh_private_key_file = var.ssh_private_key

  qemuargs = [
    ["-cdrom", local.seed_iso]
  ]

  # Keep build SSH access until Packer has authenticated to request shutdown.
  shutdown_command = "sudo /bin/bash -c 'rm -f -- /home/ubuntu/.ssh/authorized_keys /root/.ssh/authorized_keys /etc/ssh/ssh_host_* && /sbin/shutdown -P now'"
  shutdown_timeout = "5m"

  disk_size = "20G"
}

build {
  sources = ["source.qemu.ubuntu2404"]

  provisioner "shell" {
    inline = [
      "sudo apt-get update -qq",
      "sudo apt-get install -y -qq qemu-guest-agent curl vim git",
      "sudo systemctl enable --now qemu-guest-agent"
    ]
  }

  # Last guest provisioner: remove instance-specific state before shutdown.
  provisioner "shell" {
    script          = "${path.root}/seal-image.sh"
    execute_command = "sudo bash '{{ .Path }}'"
  }
}
