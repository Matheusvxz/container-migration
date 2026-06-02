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
      image = each.value.is_controller ? data.google_compute_image.controller_debian.self_link : data.google_compute_image.custom_debian.self_link
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

# Provisionamento automático do orquestrador/controller
resource "terraform_data" "install_controller" {
  for_each = {
    for k, v in var.virtual_machines : k => v
    if v.is_controller && !var.delete_virtual_machines
  }

  triggers_replace = [
    google_compute_instance.compute_instances[each.key].id,
    join(",", [for vm in google_compute_instance.compute_instances : vm.id])
  ]

  connection {
    type        = "ssh"
    user        = "dev"
    private_key = file(replace(var.ssh_public_key_path, ".pub", ""))
    host        = google_compute_instance.compute_instances[each.key].network_interface[0].access_config[0].nat_ip
  }

  # Copia a pasta de segredos (para que install.sh encontre ../secrets/key)
  provisioner "file" {
    source      = "${path.module}/../../secrets"
    destination = "/home/dev/secrets"
  }

  # Copia a pasta de código python do orquestrador
  provisioner "file" {
    source      = "${path.module}/../../python"
    destination = "/home/dev/python"
  }

  # Copia a pasta de arquivos de configuração dos pods/contêineres
  provisioner "file" {
    source      = "${path.module}/../../files"
    destination = "/home/dev/files"
  }

  # Executa a geração do hosts.txt com os IPs internos de todas as VMs
  # e inicia o script de instalação install.sh
  provisioner "remote-exec" {
    inline = [
      "mkdir -p /home/dev/python",
      "cat <<'EOF' > /home/dev/python/hosts.txt",
      join("\n", [for vm in google_compute_instance.compute_instances : vm.network_interface[0].network_ip]),
      "EOF",
      "chmod +x /home/dev/python/scripts/install.sh",
      "sudo bash /home/dev/python/scripts/install.sh"
    ]
  }

  depends_on = [
    google_compute_instance.compute_instances
  ]
}
