packer {
  required_plugins {
    googlecompute = {
      version = ">= 1.1.4"
      source  = "github.com/hashicorp/googlecompute"
    }
  }
}

source "googlecompute" "debian" {
  project_id          = var.project_id
  source_image_family = "debian-13" # Debian 13 é o codinome Trixie
  zone                = var.zone
  image_name          = "custom-debian-crio-criu-{{timestamp}}"
  image_description   = "Debian Trixie (13) com rsync, CRI-O e CRIU compilado via source"
  ssh_username        = "packer"
  network             = var.network
  subnetwork          = var.subnetwork
  use_iap             = true
  disk_size           = 10
  
  // Usando e2-medium para a build ser mais rápida, já que compilar C (CRIU) exige um pouco de CPU e RAM.
  machine_type        = "e2-small" 
}

build {
  sources = ["source.googlecompute.debian"]

  provisioner "shell" {
    // Passando as variáveis do Packer para dentro do script bash
    environment_vars = [
      "CRIU_VERSION=${var.criu_version}",
      "CRIO_VERSION=${var.crio_version}",
      "CNI_VERSION=${var.cni_version}"
    ]
    script = "scripts/setup.sh"
    
    // Roda o script como root
    execute_command = "chmod +x {{ .Path }}; sudo {{ .Vars }} {{ .Path }}"
  }
}
