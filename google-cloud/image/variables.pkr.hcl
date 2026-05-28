variable "project_id" {
  type        = string
  description = "The GCP Project ID onde a imagem será construída"
  default     = "MEU_PROJETO_GCP_ID"
}

variable "zone" {
  type        = string
  description = "A zona do GCP que será usada na build"
  default     = "us-central1-a"
}

variable "criu_version" {
  type        = string
  description = "Versão do CRIU para clonar e compilar a partir do código fonte (ex: v3.19, v4.0)"
  default     = "v3.19"
}

variable "crio_version" {
  type        = string
  description = "Versão do repositório do CRI-O a ser instalado (ex: v1.28, v1.30)"
  default     = "v1.28"
}

variable "cni_version" {
  type        = string
  description = "Versão oficial dos plugins CNI a ser instalada a partir do GitHub (ex: v1.5.1)"
  default     = "v1.5.1"
}

variable "network" {
  type        = string
  description = "A rede VPC onde a VM temporária será criada"
  default     = "default"
}

variable "subnetwork" {
  type        = string
  description = "A sub-rede (subnet) onde a VM será criada. Obrigatório se a VPC for 'custom mode'"
  default     = ""
}
