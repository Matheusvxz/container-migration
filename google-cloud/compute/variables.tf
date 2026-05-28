# data "external" "env" {
#   program = ["${path.module}/env.sh"]
# }

variable "project_id" {
  type    = string
  default = ""
}

variable "default_region" {
  type    = string
  default = ""
}

variable "default_zone" {
  type    = string
  default = ""
}

variable "run_virtual_machines" {
  type    = bool
  default = true
}

variable "delete_virtual_machines" {
  type    = bool
  default = false
}


variable "ssh_public_key_path" {
  description = "SSH public key for the virtual machines"
  type        = string
  default     = ""
}

variable "image_name" {
  description = "Nome da imagem customizada gerada pelo Packer"
  type        = string
  default     = ""
}

variable "image_project" {
  description = "Projeto da imagem"
  type        = string
  nullable    = true
}

# # Locals para usar os valores do .env como padrão
# locals {
#   project_id       = var.project_id != "" ? var.project_id : data.external.env.result.project_id
#   default_region   = var.default_region != "" ? var.default_region : data.external.env.result.default_region
#   default_zone     = var.default_zone != "" ? var.default_zone : data.external.env.result.default_zone
# }

variable "subnet" {
  description = "Configuração das sub-redes"
  type = map(object({
    subnet_cidr   = string
    subnet_region = string
  }))
  default = {
    "us-central1" = {
      subnet_cidr   = "10.128.0.0/24"
      subnet_region = "us-central1"
    }
  }
}

variable "virtual_machines" {
  description = "Map of virtual machines to create"
  type = map(object({
    name          = string
    machine_type  = string
    zone          = string
    subnet_region = string
  }))
  default = {
    host-1 = {
      name          = "host-1"
      machine_type  = "e2-medium"
      zone          = "us-central1-a"
      subnet_region = "us-central1"
    }
  }
}
