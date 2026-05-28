# Imagem Debian 13 customizada gerada pelo Packer (com CRI-O e CRIU)
data "google_compute_image" "custom_debian" {
  project = var.image_project != null ? var.image_project : var.project_id
  name    = var.image_name
}
