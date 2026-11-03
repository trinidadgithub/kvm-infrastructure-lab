output "vm_names" {
  value = module.compute.vm_names
}

output "vm_uuids" {
  value = module.compute.vm_uuids
}

output "vm_ips" {
  description = "Declared DHCP reservation for the disposable regression VM, not a discovered guest address."
  value       = { for name, vm in var.vms : name => vm.ip }
}

output "network_name" {
  value = libvirt_network.pty_regression.name
}

output "pool_name" {
  value = libvirt_pool.pty_regression.name
}
