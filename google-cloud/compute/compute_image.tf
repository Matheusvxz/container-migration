# Imagem Debian 13 customizada gerada pelo Packer (com CRI-O e CRIU)
data "google_compute_image" "custom_debian" {
  project = var.image_project != null ? var.image_project : var.project_id
  name    = var.image_name
}

# Imagem Debian 13 customizada do controller gerada pelo Packer
data "google_compute_image" "controller_debian" {
  project = var.image_project != null ? var.image_project : var.project_id
  name    = var.controller_image_name != "" ? var.controller_image_name : var.image_name
}
