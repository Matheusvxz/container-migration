locals {
  network_name = "vpc-network"
  enable_apis  = true
}

module "project-services-apis" {
  source                      = "terraform-google-modules/project-factory/google//modules/project_services"
  version                     = "18.2.0"
  disable_services_on_destroy = false

  project_id  = var.project_id
  enable_apis = local.enable_apis

  activate_apis = [
    "cloudapis.googleapis.com",
    # "cloudbuild.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "storage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_service_account" "service_accounts" {
  for_each = {
    for sa in [
      {
        name        = "Simple Compute Engine SA",
        email       = "simple-compute-engine",
        description = "Simple service account attached to VM"
      }
    ] : sa.email => sa
  }

  account_id   = each.value.email
  display_name = each.value.name
  description  = each.value.description
}

# ## Setting IAM Permissions ##
resource "google_project_iam_member" "iam_compute_sa" {
  for_each = toset([
    "roles/storage.objectAdmin",
    "roles/compute.admin",
    "roles/iam.serviceAccountUser"
  ])

  role    = each.key
  project = var.project_id
  member  = "serviceAccount:${google_service_account.service_accounts["simple-compute-engine"].email}"
}
