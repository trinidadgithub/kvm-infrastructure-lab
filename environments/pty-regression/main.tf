locals {
  ssh_public_key = trimspace(file(var.ssh_public_key_path))
  network_number = sum([
    for index, octet in split(".", split("/", var.network_cidr)[0]) : parseint(octet, 10) * pow(256, 3 - index)
  ])
  network_block_size = pow(2, 32 - parseint(split("/", var.network_cidr)[1], 10))
  gateway_number = sum([
    for index, octet in split(".", var.gateway_ip) : parseint(octet, 10) * pow(256, 3 - index)
  ])
  dhcp_start_number = sum([
    for index, octet in split(".", var.dhcp_start) : parseint(octet, 10) * pow(256, 3 - index)
  ])
  dhcp_end_number = sum([
    for index, octet in split(".", var.dhcp_end) : parseint(octet, 10) * pow(256, 3 - index)
  ])
  reserved_ip_numbers = [for vm in values(var.vms) : sum([
    for index, octet in split(".", vm.ip) : parseint(octet, 10) * pow(256, 3 - index)
  ])]
  compute_vms = {
    for name, vm in var.vms : name => {
      memory = vm.memory_mib
      vcpu   = vm.vcpu
      disk   = vm.disk_gib * 1024 * 1024 * 1024
      mac    = vm.mac
    }
  }
  cloudinit_data = {
    for name, vm in var.vms : name => {
      user_data = templatefile("${path.module}/../../cloud-init/ubuntu-user-data.tftpl", {
        hostname   = vm.hostname
        public_key = local.ssh_public_key
      })
      meta_data = templatefile("${path.module}/../../cloud-init/meta-data.tftpl", {
        hostname = vm.hostname
      })
    }
  }
}

resource "libvirt_pool" "pty_regression" {
  name = var.pool_name
  type = "dir"
  target = {
    path = var.pool_path
    permissions = {
      mode  = "0770"
      owner = "0"
      group = var.pool_group_id
    }
  }

  lifecycle {
    precondition {
      condition     = !startswith(var.base_image, "${trimsuffix(var.pool_path, "/")}/")
      error_message = "The host-owned backing image must be outside this disposable environment's Terraform-owned pool."
    }
    precondition {
      condition     = filesha256(var.base_image) == var.base_image_sha256
      error_message = "The published v1 image checksum does not match base_image_sha256; stop and verify the host-owned image before proceeding."
    }
  }
}

resource "libvirt_network" "pty_regression" {
  name = var.network_name
  bridge = {
    name  = var.bridge_name
    stp   = "on"
    delay = "0"
  }
  forward = {
    mode = "nat"
    nat = {
      ports = [{ start = 1024, end = 65535 }]
    }
  }
  ips = [{
    address = var.gateway_ip
    netmask = cidrnetmask(var.network_cidr)
    dhcp = {
      hosts  = [for name, vm in var.vms : { mac = vm.mac, name = vm.hostname, ip = vm.ip }]
      ranges = [{ start = var.dhcp_start, end = var.dhcp_end }]
    }
  }]

  lifecycle {
    precondition {
      condition = (alltrue([
        for ip in concat([local.gateway_number, local.dhcp_start_number, local.dhcp_end_number], local.reserved_ip_numbers) :
        floor(ip / local.network_block_size) == floor(local.network_number / local.network_block_size)
        ]) && !contains(local.reserved_ip_numbers, local.gateway_number) &&
        (local.gateway_number < local.dhcp_start_number || local.gateway_number > local.dhcp_end_number) &&
        local.dhcp_start_number <= local.dhcp_end_number &&
      alltrue([for ip in local.reserved_ip_numbers : ip < local.dhcp_start_number || ip > local.dhcp_end_number]))
      error_message = "Gateway, DHCP range and VM reservations must be in the subnet; reservations must not use the gateway or DHCP dynamic range."
    }
  }
}

module "compute" {
  source = "../../terraform/modules/compute"

  vms                   = local.compute_vms
  pool_name             = libvirt_pool.pty_regression.name
  network_name          = libvirt_network.pty_regression.name
  base_image            = var.base_image
  cloudinit_data        = local.cloudinit_data
  cloudinit_in_pool     = true
  enable_guest_agent    = true
  enable_serial_console = false
}
