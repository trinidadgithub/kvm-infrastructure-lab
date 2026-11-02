variable "vms" {
  type = map(object({
    memory = number
    vcpu   = number
    disk   = number
    mac    = string
  }))
}

variable "pool_name" {
  type = string
}

variable "network_name" {
  type = string
}

variable "base_image" {
  type = string
}

variable "cloudinit_data" {
  type = map(object({
    user_data = string
    meta_data = string
  }))
}

variable "cloudinit_in_pool" {
  description = "Upload generated cloud-init ISOs into pool-owned volumes (opt-in; existing domains retain their original disk paths)."
  type        = bool
  default     = false
}

variable "enable_guest_agent" {
  description = "Expose the QEMU guest-agent virtio channel to guest VMs."
  type        = bool
  default     = false
}

variable "enable_serial_console" {
  description = "Configure an explicit PTY-backed serial console."
  type        = bool
  default     = true
}
