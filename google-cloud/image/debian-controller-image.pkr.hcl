source "googlecompute" "controller" {
  project_id          = var.project_id
  source_image_family = "debian-13" # Debian 13 é o codinome Trixie
  zone                = var.zone
  image_name          = "custom-debian-controller-{{timestamp}}"
  image_description   = "Imagem do Controller Debian Trixie (13) com dependencias Python, gRPC e asyncssh para o orquestrador"
  ssh_username        = "packer"
  network             = var.network
  subnetwork          = var.subnetwork
  use_iap             = true
  disk_size           = 10
  
  // Como é apenas instalação de pacotes Python comuns, e2-small é suficiente.
  machine_type        = "e2-small" 
}

build {
  sources = ["source.googlecompute.controller"]

  provisioner "shell" {
    script = "scripts/setup-controller.sh"
    
    // Roda o script de provisionamento como root
    execute_command = "chmod +x {{ .Path }}; sudo {{ .Vars }} {{ .Path }}"
  }
}
