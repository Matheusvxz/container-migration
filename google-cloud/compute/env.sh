#!/bin/sh

# env.sh
# Carrega variáveis do arquivo .env e retorna como JSON para o Terraform

# Lê o arquivo .env se existir
if [ -f "../../.env" ]; then
  # Exporta variáveis do arquivo .env (removendo comentários e linhas em branco)
  export $(grep -v '^#' ../../.env | xargs)
fi

# Retorna as variáveis como JSON válido
cat <<EOF
{
  "project_id": "${GCP_PROJECT_ID}",
  "default_region": "${GCP_DEFAULT_REGION}",
  "default_zone": "${GCP_DEFAULT_ZONE}",
  "image_name": "${IMAGE_NAME}",
  "ssh_public_key_path": $(realpath ../../$SSH_PUBLIC_KEY_PATH)
}
EOF
