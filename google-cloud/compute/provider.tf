terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "7.33"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "7.33"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.default_region
  zone    = var.default_zone
}

provider "google-beta" {
  project = var.project_id
  region  = var.default_region
  zone    = var.default_zone
}
