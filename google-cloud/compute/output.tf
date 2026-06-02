output "vm_ips" {
  description = "External IPs of all VM instances"
  value = var.delete_virtual_machines ? [] : [
    for vm in google_compute_instance.compute_instances : vm.network_interface[0].access_config[0].nat_ip
  ]
}

output "vm_details" {
  description = "Detailed information about all VM instances"
  value = var.delete_virtual_machines || !var.run_virtual_machines ? {} : {
    for key, vm in google_compute_instance.compute_instances : key => {
      name         = vm.name
      machine_type = vm.machine_type
      zone         = vm.zone
      external_ip  = vm.network_interface[0].access_config[0].nat_ip
      internal_ip  = vm.network_interface[0].network_ip
      status       = vm.current_status
    }
  }
}

output "vm_ssh_commands" {
  description = "SSH commands to connect to each VM"
  value = var.delete_virtual_machines ? {} : {
    for key, vm in google_compute_instance.compute_instances : key =>
    "gcloud compute ssh ${vm.name} --zone=${vm.zone} --project=${var.project_id}"
  }
}

# output "storage_checkpoint" {
#   description = "Cloud Storage bucket for checkpoints"
#   value       = google_storage_bucket.checkpoint
# }

output "controller_details" {
  description = "Detailed information about the controller VM"
  value = var.delete_virtual_machines || !var.run_virtual_machines ? {} : {
    for key, vm in google_compute_instance.compute_instances : key => {
      name         = vm.name
      external_ip  = vm.network_interface[0].access_config[0].nat_ip
      internal_ip  = vm.network_interface[0].network_ip
      ssh_command  = "ssh -i ${replace(var.ssh_public_key_path, ".pub", "")} dev@${vm.network_interface[0].access_config[0].nat_ip}"
    } if var.virtual_machines[key].is_controller
  }
}
