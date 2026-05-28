# resource "google_storage_bucket" "checkpoint" {
#   name          = "${local.project_id}-checkpoint"
#   location      = "US-CENTRAL1"
#   force_destroy = true

#   uniform_bucket_level_access = true
#   public_access_prevention    = "enforced"
# }
