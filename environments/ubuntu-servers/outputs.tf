output "vm_names" {
  value = module.compute.vm_names
}

output "vm_uuids" {
  value = module.compute.vm_uuids
}

output "vm_ips" {
  description = "Declared DHCP reservations, not discovered guest addresses."
  value       = { for name, vm in var.vms : name => vm.ip }
}

output "network_name" {
  value = libvirt_network.ubuntu_servers.name
}

output "pool_name" {
  value = libvirt_pool.ubuntu_servers.name
}
