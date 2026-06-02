#!/bin/bash
set -e

# Configura o apt para modo não-interativo para evitar popups travando o build do Packer
export DEBIAN_FRONTEND=noninteractive

echo "=== 1. Atualizando repositórios de pacotes ==="
apt-get update -y
apt-get upgrade -y

echo "=== 2. Instalando ferramentas essenciais de rede e utilitários ==="
apt-get install -y \
    curl \
    wget \
    git \
    rsync \
    ssh \
    unzip \
    ca-certificates

echo "=== 3. Instalando Python 3, Pip e Virtualenv ==="
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-full \
    python3-dev \
    build-essential

# Verifica as versões instaladas
python3 --version
pip3 --version

echo "=== 4. Instalando dependências de Python globais para o Orquestrador ==="
# Debian 13 trixie implementa o PEP 668 que impede o pip install global.
# Usamos a flag --break-system-packages para garantir a instalação global das bibliotecas do orquestrador
# a fim de que qualquer usuário logado possa importar ou rodar os scripts imediatamente.
pip3 install --break-system-packages \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    asyncssh>=2.14.0 \
    protobuf>=4.25.0

echo "=== 5. Verificando instalações de pacotes Python ==="
python3 -c "import grpc; print('gRPC version:', grpc.__version__)"
python3 -c "import asyncssh; print('AsyncSSH version:', asyncssh.__version__)"
python3 -c "import google.protobuf; print('Protobuf version:', google.protobuf.__version__)"

echo "=== 6. Configurações Finais de Ambiente ==="
# Opcional: Adiciona alias ou configurações globais caso necessário no futuro
echo "Configuração da imagem do controlador finalizada com SUCESSO!"
