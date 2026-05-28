terraform {
  backend "gcs" {
    bucket  = "terraform-state-each-master"
    prefix  = "terraform/migration"
  }
}
