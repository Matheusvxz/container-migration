#!/bin/bash
# ==============================================================================
# Script de Instalação do Orquestrador de Migração (Daemon & CLI Wrapper)
# ==============================================================================
set -e

INSTALL_DIR="/opt/migration-orchestrator"
SERVICE_FILE="/etc/systemd/system/migration-daemon.service"
CLI_WRAPPER="/usr/local/bin/migration-cli"

echo "=== [1/7] Criando pasta de instalação e acertando permissões ==="
sudo mkdir -p "$INSTALL_DIR"
sudo chown -R dev:dev "$INSTALL_DIR"

echo "=== [2/7] Copiando arquivos do Orquestrador ==="
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Limpa códigos antigos para evitar arquivos órfãos (preservando hosts.txt e chaves SSH)
rm -f "$INSTALL_DIR"/*.py
rm -rf "$INSTALL_DIR"/src
rm -rf "$INSTALL_DIR"/proto

# Copia a estrutura do pacote e definições
cp -r "$PROJECT_ROOT"/src "$INSTALL_DIR"/
cp -r "$PROJECT_ROOT"/proto "$INSTALL_DIR"/
cp "$PROJECT_ROOT"/pyproject.toml "$INSTALL_DIR"/
cp "$PROJECT_ROOT"/README.md "$INSTALL_DIR"/

# Copia ou cria o hosts.txt inicial
if [ -f "$PROJECT_ROOT/hosts.txt" ]; then
    cp "$PROJECT_ROOT/hosts.txt" "$INSTALL_DIR"/
else
    echo "# Adicione um IP por linha" > "$INSTALL_DIR/hosts.txt"
fi

# Copia a chave de segurança SSH interna
if [ -f "$PROJECT_ROOT/../secrets/key" ]; then
    cp "$PROJECT_ROOT/../secrets/key" "$INSTALL_DIR/key"
    chmod 600 "$INSTALL_DIR/key"
    echo "Chave SSH copiada com sucesso."
else
    echo "Aviso: Chave SSH secreta (../secrets/key) não encontrada na pasta atual."
    echo "Por favor, coloque a chave em $INSTALL_DIR/key manualmente após a instalação."
fi

echo "=== [3/7] Inicializando Ambiente Virtual (venv) ==="
python3 -m venv "$INSTALL_DIR/.venv"

echo "=== [4/7] Instalando Pacote e Dependências ==="
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install "$INSTALL_DIR"

echo "=== [5/7] Compilando Stubs gRPC de Comunicação ==="
# Compila o arquivo migration.proto utilizando o grpc_tools do venv para o diretório de stubs
"$INSTALL_DIR/.venv/bin/python" -m grpc_tools.protoc \
    -I"$INSTALL_DIR/proto" \
    --python_out="$INSTALL_DIR/src/orchestrator/proto" \
    --grpc_python_out="$INSTALL_DIR/src/orchestrator/proto" \
    "$INSTALL_DIR/proto/migration.proto"

# Garante que o __init__.py dos stubs esteja configurado (ja copiado de src/, mas por garantia)
if [ ! -f "$INSTALL_DIR/src/orchestrator/proto/__init__.py" ]; then
    echo -e "import sys\nimport os\nsys.path.insert(0, os.path.dirname(__file__))" > "$INSTALL_DIR/src/orchestrator/proto/__init__.py"
fi

echo "=== [6/7] Instalando o Serviço Systemd (migration-daemon) ==="
sudo cp "$SCRIPT_DIR/migration-daemon.service" "$SERVICE_FILE"
# Garante a propriedade de todo o diretório para o usuário dev antes de iniciar o daemon
sudo chown -R dev:dev "$INSTALL_DIR"
sudo systemctl daemon-reload
sudo systemctl enable migration-daemon.service
sudo systemctl restart migration-daemon.service
echo "Serviço daemon registrado e iniciado com sucesso via systemctl!"

echo "=== [7/7] Registrando o Link Global da CLI (migration-cli) ==="
# Cria o link simbólico global apontando para o binário gerado pelo pip no venv
sudo ln -sf "$INSTALL_DIR/.venv/bin/migration-cli" "$CLI_WRAPPER"
echo "CLI registrada globalmente via link simbólico! Você já pode usar o comando 'migration-cli' de qualquer pasta."

echo "=========================================================================="
echo " INSTALAÇÃO CONCLUÍDA COM SUCESSO!"
echo "--------------------------------------------------------------------------"
echo " - Serviço Daemon rodando em background (Porta 50051)"
echo " - CLI disponível globalmente via comando: 'migration-cli'"
echo " - Pasta de Instalação: $INSTALL_DIR"
echo " - Arquivo de Hosts: $INSTALL_DIR/hosts.txt (Edite para alterar nós)"
echo ""
echo " Exemplo de uso:"
echo "   migration-cli list"
echo "   migration-cli refresh"
echo "=========================================================================="
