#**************************************************************************
#*                         VIRTUAL MACHINE CONFIGURATION                  **
#*************************************************************************#

locals {
  # Create a map of region to subnet index for easier lookup
  subnet_index_by_region = {
    for idx, key in keys(var.subnet) : var.subnet[key].subnet_region => idx
  }
}

resource "google_compute_instance" "compute_instances" {
  for_each = var.delete_virtual_machines ? {} : var.virtual_machines

  name         = each.value.name
  machine_type = each.value.machine_type
  zone         = each.value.zone

  desired_status = var.run_virtual_machines ? "RUNNING" : "TERMINATED"

  boot_disk {
    initialize_params {
      image = data.google_compute_image.custom_debian.self_link
      size  = 20
    }
  }

  tags = ["allow-external-ssh"]

  metadata = {
    "ssh-keys" = <<EOT
      dev:${file(var.ssh_public_key_path)}
    EOT
  }

  network_interface {
    network    = module.vpc-network.network_name
    subnetwork = module.vpc-network.subnets_self_links[local.subnet_index_by_region[each.value.subnet_region]]
    access_config {
      # Cria um IP externo público temporário (assim como no mpi-environment)
    }
  }

  service_account {
    email  = google_service_account.service_accounts["simple-compute-engine"].email
    scopes = ["cloud-platform"]
  }

  lifecycle {
    ignore_changes = [
      metadata,
    ]
  }

  depends_on = [module.project-services-apis]
}
