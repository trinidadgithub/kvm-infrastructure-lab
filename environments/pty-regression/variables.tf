variable "libvirt_uri" {
  description = "Local libvirt connection for this disposable regression environment."
  type        = string
  default     = "qemu:///system"

  validation {
    condition     = var.libvirt_uri == "qemu:///system"
    error_message = "The PTY regression root is intentionally limited to the local qemu:///system connection."
  }
}

variable "pool_name" {
  description = "Dedicated disposable libvirt pool name."
  type        = string
  default     = "pty-regression"

  validation {
    condition     = var.pool_name == "pty-regression"
    error_message = "Use the dedicated pool name pty-regression."
  }
}

variable "pool_path" {
  description = "Dedicated disposable pool directory; it must not cover the host-owned base image or existing environments."
  type        = string
  default     = "/var/lib/libvirt/images/labs/pty-regression"

  validation {
    condition     = var.pool_path == "/var/lib/libvirt/images/labs/pty-regression"
    error_message = "Use the dedicated pool path /var/lib/libvirt/images/labs/pty-regression."
  }
}

variable "pool_group_id" {
  description = "Numeric group ID for QEMU access on this host; look up with getent group libvirt-qemu."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.pool_group_id))
    error_message = "pool_group_id must be a numeric group ID determined on the target host."
  }
}

variable "base_image" {
  description = "Absolute path to the already published, immutable Ubuntu 24.04 v1 qcow2."
  type        = string
  default     = "/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2"

  validation {
    condition     = startswith(var.base_image, "/") && basename(var.base_image) == "ubuntu-24.04-v1.qcow2"
    error_message = "base_image must be the absolute path to the published ubuntu-24.04-v1.qcow2 image."
  }
}

variable "base_image_sha256" {
  description = "Expected SHA-256 of the published v1 image, verified during plan."
  type        = string
  default     = "4d6565fd43a775899b03730e72daca4669f8c71ce57e31482b5520965aef790d"

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.base_image_sha256))
    error_message = "base_image_sha256 must be a lowercase 64-character SHA-256 hex digest."
  }
}

variable "ssh_public_key_path" {
  description = "Absolute path to the SSH public key injected into the disposable guest."
  type        = string

  validation {
    condition     = startswith(var.ssh_public_key_path, "/")
    error_message = "ssh_public_key_path must be an absolute path."
  }
}

variable "network_name" {
  description = "Dedicated disposable libvirt network name."
  type        = string
  default     = "pty-regression-net"

  validation {
    condition     = var.network_name == "pty-regression-net"
    error_message = "Use the dedicated network name pty-regression-net."
  }
}

variable "bridge_name" {
  description = "Dedicated disposable bridge name; must not collide with existing libvirt bridges."
  type        = string
  default     = "virbr3"

  validation {
    condition     = var.bridge_name == "virbr3"
    error_message = "Use the dedicated bridge name virbr3."
  }
}

variable "network_cidr" {
  description = "Dedicated disposable subnet, verified collision-free by the preflight script."
  type        = string
  default     = "192.168.125.0/24"

  validation {
    condition     = var.network_cidr == "192.168.125.0/24"
    error_message = "Use the dedicated subnet 192.168.125.0/24."
  }
}

variable "gateway_ip" {
  type    = string
  default = "192.168.125.1"

  validation {
    condition     = var.gateway_ip == "192.168.125.1"
    error_message = "Use the dedicated gateway 192.168.125.1."
  }
}

variable "dhcp_start" {
  type    = string
  default = "192.168.125.100"

  validation {
    condition     = var.dhcp_start == "192.168.125.100"
    error_message = "Use the dedicated DHCP range start 192.168.125.100."
  }
}

variable "dhcp_end" {
  type    = string
  default = "192.168.125.200"

  validation {
    condition     = var.dhcp_end == "192.168.125.200"
    error_message = "Use the dedicated DHCP range end 192.168.125.200."
  }
}

variable "vms" {
  description = "Exactly one disposable regression VM with a reserved identity."
  type = map(object({
    hostname   = string
    vcpu       = number
    memory_mib = number
    disk_gib   = number
    mac        = string
    ip         = string
  }))

  default = {
    "pty-regression-01" = {
      hostname   = "pty-regression-01"
      vcpu       = 2
      memory_mib = 2048
      disk_gib   = 20
      mac        = "52:54:00:cc:00:01"
      ip         = "192.168.125.10"
    }
  }

  validation {
    condition = (
      length(var.vms) == 1 &&
      alltrue([
        for name, vm in var.vms :
        name == "pty-regression-01" &&
        vm.hostname == "pty-regression-01" &&
        vm.mac == "52:54:00:cc:00:01" &&
        vm.ip == "192.168.125.10" &&
        vm.vcpu > 0 &&
        vm.memory_mib > 0 &&
        vm.disk_gib >= 20
      ])
    )
    error_message = "Use exactly one VM named pty-regression-01 with MAC 52:54:00:cc:00:01, IP 192.168.125.10, positive CPU/RAM and at least 20 GiB disk."
  }
}
