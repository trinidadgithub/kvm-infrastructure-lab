variable "libvirt_uri" {
  description = "Connection to the intended workstation's libvirt daemon."
  type        = string
  default     = "qemu:///system"
}

variable "pool_name" {
  type    = string
  default = "ubuntu-servers"
}

variable "pool_path" {
  description = "Dedicated libvirt pool directory beneath a host-owned filesystem/dataset."
  type        = string
  default     = "/var/lib/libvirt/images/labs/ubuntu-servers"

  validation {
    condition     = startswith(var.pool_path, "/") && var.pool_path != "/"
    error_message = "pool_path must be an absolute directory path."
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
  description = "Absolute path to the already published, immutable qcow2 on this host (outside the environment pool)."
  type        = string

  validation {
    condition     = startswith(var.base_image, "/")
    error_message = "base_image must be an absolute path on the libvirt host."
  }
}

variable "ssh_public_key_path" {
  description = "Absolute path to the SSH public key to inject into guests."
  type        = string

  validation {
    condition     = startswith(var.ssh_public_key_path, "/")
    error_message = "ssh_public_key_path must be an absolute path."
  }
}

variable "network_name" {
  type    = string
  default = "ubuntu-servers-net"
}

variable "bridge_name" {
  type    = string
  default = "virbr2"
}

variable "network_cidr" {
  type    = string
  default = "192.168.124.0/24"

  validation {
    condition     = can(cidrnetmask(var.network_cidr))
    error_message = "network_cidr must be a valid IPv4 CIDR."
  }
}

variable "gateway_ip" {
  type    = string
  default = "192.168.124.1"

  validation {
    condition     = can(cidrhost("${var.gateway_ip}/32", 0))
    error_message = "gateway_ip must be an IPv4 address."
  }
}

variable "dhcp_start" {
  type    = string
  default = "192.168.124.100"

  validation {
    condition     = can(cidrhost("${var.dhcp_start}/32", 0))
    error_message = "dhcp_start must be an IPv4 address."
  }
}

variable "dhcp_end" {
  type    = string
  default = "192.168.124.200"

  validation {
    condition     = can(cidrhost("${var.dhcp_end}/32", 0))
    error_message = "dhcp_end must be an IPv4 address."
  }
}

variable "vms" {
  description = "Domain names as keys; disk_gib is virtual capacity, not upfront physical ZFS allocation."
  type = map(object({
    hostname   = string
    vcpu       = number
    memory_mib = number
    disk_gib   = number
    mac        = string
    ip         = string
  }))

  validation {
    condition = (length(var.vms) > 0 && alltrue([
      for name, vm in var.vms :
      can(regex("^[a-z0-9][a-z0-9-]*$", name)) &&
      can(regex("^[a-z0-9][a-z0-9-]*$", vm.hostname)) &&
      vm.vcpu > 0 && vm.memory_mib > 0 && vm.disk_gib > 0 &&
      can(regex("^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$", vm.mac)) &&
      can(cidrhost("${vm.ip}/32", 0))
      ]) && length(distinct([for vm in values(var.vms) : lower(vm.mac)])) == length(var.vms) &&
      length(distinct([for vm in values(var.vms) : vm.ip])) == length(var.vms) &&
    length(distinct([for vm in values(var.vms) : vm.hostname])) == length(var.vms))
    error_message = "Supply unique VM hostnames/MACs/IPs, valid names and IPv4 addresses, and positive CPU/RAM/disk sizes (verify disk >= image virtual size separately)."
  }
}
