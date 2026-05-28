#**************************************************************************
#*                         NETWORK CONFIGURATION                         **
#*************************************************************************#

###################### Virtual Private Clouds - VPCs ######################
module "vpc-network" {
  source  = "terraform-google-modules/network/google"
  version = "~> 18.1"

  project_id   = var.project_id
  network_name = local.network_name
  mtu          = 1460
  routing_mode = "REGIONAL"

  firewall_rules = [
    {
      name    = "default-allow-custom"
      network = local.network_name

      description = "Allows connection from any source to any instance on the network using custom protocols.",

      direction = "INGRESS"

      ranges = [
        "10.128.0.0/16"
      ]
      priority = "65534"

      target_tags = []

      allow = [
        {
          protocol = "all"
          ports    = null
        }
      ]
    },
    {
      name      = "allow-ingress-from-iap"
      network   = local.network_name
      direction = "INGRESS"
      ranges = [
        "35.235.240.0/20"
      ]
      allow = [
        {
          protocol = "tcp"
          ports    = ["22", "3389"]
        }
      ]
    },
    {
      name      = "allow-ssh-ingress"
      network   = local.network_name
      direction = "INGRESS"
      ranges = [
        "0.0.0.0/0"
      ]
      target_tags = ["allow-external-ssh"]
      allow = [
        {
          protocol = "tcp"
          ports    = ["22"]
        }
      ]
    }
  ]

  # Subnet configuration for the VPC
  subnets = [
    for key, subnet in var.subnet : {
      subnet_name           = key
      subnet_ip             = subnet.subnet_cidr
      subnet_region         = subnet.subnet_region
      subnet_private_access = true
    }
  ]
}
