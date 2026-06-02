#!/bin/bash
# O Packer configura 'set -e' por padrão no provisioner, mas é bom garantir.
# Isso faz o script parar imediatamente se qualquer comando der erro.
set -e

echo "========================================="
echo " Iniciando setup da Imagem..."
echo " Versão do CRIU: ${CRIU_VERSION}"
echo " Versão do CRI-O: ${CRIO_VERSION}"
echo " Versão do CNI: ${CNI_VERSION}"
echo "========================================="

# Evita que o apt-get faça perguntas interativas (ex: timezone)
export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------
echo ">>> 1. Atualizando sistema e instalando utilitários básicos..."
# ---------------------------------------------------------
apt-get update -y
apt-get upgrade -y
apt-get install -y rsync curl wget git build-essential pkg-config gnupg

# ---------------------------------------------------------
echo ">>> 2. Configurando Kernel Modules e Sysctl para Contêineres..."
# ---------------------------------------------------------
# O Kubernetes e o CRI-O precisam desses módulos de kernel carregados e configurações de rede
cat <<EOF > /etc/modules-load.d/crio.conf
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter

cat <<EOF > /etc/sysctl.d/99-kubernetes-cri.conf
net.bridge.bridge-nf-call-iptables  = 1
net.ipv4.ip_forward                 = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF

sysctl --system

# ---------------------------------------------------------
echo ">>> 3. Instalando pacotes de sistema necessários (Rede e Segurança)..."
# ---------------------------------------------------------
# Utilitários vitais exigidos pelo Kubernetes e plugins CNI para roteamento e segurança
apt-get install -y iptables iproute2 socat libseccomp2 ebtables ethtool

# ---------------------------------------------------------
echo ">>> 4. Instalando CRIU e checkpointctl nativos do sistema..."
# ---------------------------------------------------------
# Instalamos o CRIU, suas bibliotecas e a ferramenta checkpointctl diretamente dos repositórios oficiais
# do Debian para garantir total compatibilidade de glibc e versão 4.1.1+
apt-get install -y criu libcriu2 libcriu-dev checkpointctl
echo ">>> CRIU e checkpointctl instalados com sucesso."

# ---------------------------------------------------------
echo ">>> 5. Instalando CRI-O e dependências do ecossistema de contêineres..."
# ---------------------------------------------------------
mkdir -p /etc/apt/keyrings

# Adiciona a chave e o repositório oficial (ignorando validação estrita de assinatura OpenPGP v3 do Debian 13)
curl -fsSL "https://download.opensuse.org/repositories/isv:/cri-o:/stable:/${CRIO_VERSION}/deb/Release.key" | \
    gpg --dearmor -o /etc/apt/keyrings/cri-o-apt-keyring.gpg || true

echo "deb [trusted=yes] https://download.opensuse.org/repositories/isv:/cri-o:/stable:/${CRIO_VERSION}/deb/ /" | \
    tee /etc/apt/sources.list.d/cri-o.list

apt-get update -y -o Acquire::AllowInsecureRepositories=true -o Acquire::AllowDowngradeToInsecureRepositories=true || true

# Instalando o daemon principal e declarando EXPLICITAMENTE os componentes core do runtime (removendo cri-tools para download manual)
apt-get install -y --allow-unauthenticated cri-o containernetworking-plugins runc conmon

echo ">>> 5.1. Instalando crun nativo e corrigindo runtime do CRI-O..."
# Instalamos o crun nativo do Debian e substituímos a versão bugada/Nix fornecida pelo repositório do CRI-O
apt-get install -y crun
if [ -f /usr/libexec/crio/crun ]; then
    mv /usr/libexec/crio/crun /usr/libexec/crio/crun.bak
fi
ln -s /usr/bin/crun /usr/libexec/crio/crun
echo ">>> crun nativo configurado com sucesso."

echo ">>> 5.1.1. Corrigindo conflito do AppArmor com crun (Permission denied ao parar contêineres)..."
# Desabilita o perfil do crun no AppArmor caso ele exista para evitar o erro 'send signal to pidfd: Permission denied'
if [ -f /etc/apparmor.d/crun ]; then
    mkdir -p /etc/apparmor.d/disable
    if [ ! -L /etc/apparmor.d/disable/crun ]; then
        ln -s /etc/apparmor.d/crun /etc/apparmor.d/disable/
    fi
    if command -v apparmor_parser >/dev/null 2>&1; then
        apparmor_parser -R /etc/apparmor.d/crun || true
    fi
fi

echo ">>> 5.1.2 Corrigindo conflito do AppArmor com runc (Permission denied ao parar contêineres)..."
# Desabilita o perfil do runc no AppArmor caso ele exista para evitar o erro 'send signal to pidfd: Permission denied'
if [ -f /etc/apparmor.d/runc ]; then
    mkdir -p /etc/apparmor.d/disable
    if [ ! -L /etc/apparmor.d/disable/runc ]; then
        ln -s /etc/apparmor.d/runc /etc/apparmor.d/disable/
    fi
    if command -v apparmor_parser >/dev/null 2>&1; then
        apparmor_parser -R /etc/apparmor.d/runc || true
    fi
fi

echo ">>> 5.2. Configurando o CRI-O para habilitar suporte ao CRIU..."
mkdir -p /etc/crio/crio.conf.d
cat <<EOF > /etc/crio/crio.conf.d/10-crio.conf
[crio.image]
signature_policy = "/etc/crio/policy.json"

[crio.runtime]
default_runtime = "runc"
enable_criu_support = true

[crio.runtime.runtimes.crun]
runtime_path = "/usr/libexec/crio/crun"
runtime_root = "/run/crun"
monitor_path = "/usr/libexec/crio/conmon"
allowed_annotations = [
    "io.containers.trace-syscall",
]

[crio.runtime.runtimes.runc]
runtime_path = "/usr/libexec/crio/runc"
runtime_root = "/run/runc"
monitor_path = "/usr/libexec/crio/conmon"
EOF

# Baixando e instalando o cri-tools (crictl) manualmente do GitHub, pois não está presente no repositório de pacotes do CRI-O
CRI_TOOLS_VERSION="${CRIO_VERSION}.0"
curl -fsSL "https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRI_TOOLS_VERSION}/crictl-${CRI_TOOLS_VERSION}-linux-amd64.tar.gz" -o /tmp/crictl.tar.gz
tar -xzf /tmp/crictl.tar.gz -C /usr/local/bin
rm -f /tmp/crictl.tar.gz

# ---------------------------------------------------------
# CNI Plugins Fix
# O Debian 13 instala plugins desatualizados em /usr/lib/cni/ que causam erros de verificação de MAC (MAC doesn't match).
# Baixamos e instalamos os plugins oficiais da CNI em /opt/cni/bin/.
# ---------------------------------------------------------
echo ">>> 5.5. Configurando e corrigindo CNI Plugins..."
mkdir -p /opt/cni/bin
CNI_PLUGINS_VERSION="${CNI_VERSION}"
curl -fsSL "https://github.com/containernetworking/plugins/releases/download/${CNI_PLUGINS_VERSION}/cni-plugins-linux-amd64-${CNI_PLUGINS_VERSION}.tgz" -o /tmp/cni-plugins.tgz
tar -xzf /tmp/cni-plugins.tgz -C /opt/cni/bin
rm -f /tmp/cni-plugins.tgz

# Ativa a configuração padrão de rede bridge do CRI-O
if [ -f /etc/cni/net.d/10-crio-bridge.conflist.disabled ]; then
    mv /etc/cni/net.d/10-crio-bridge.conflist.disabled /etc/cni/net.d/10-crio-bridge.conflist
fi

# Habilita o serviço do CRI-O para iniciar com o sistema
systemctl daemon-reload
systemctl enable crio

# ---------------------------------------------------------
echo ">>> 5.5.5. Criando o usuário dev e configurando permissões do Sudo/Socket..."
# ---------------------------------------------------------

# 1. Cria o usuário 'dev' se não existir
if ! id "dev" &>/dev/null; then
    useradd -m -s /bin/bash dev
    echo "Usuário dev criado com sucesso."
fi

# 2. Garante que o grupo 'crio' exista e adiciona o 'dev' aos grupos 'sudo' e 'crio'
groupadd -f crio
usermod -aG sudo,crio dev

# 3. Configura o Sudo sem senha para o usuário dev
echo "dev ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/90-dev-user
chmod 440 /etc/sudoers.d/90-dev-user
echo "Permissões de Sudo sem senha para dev configuradas."

# 4. Configura o CRI-O para criar o socket UDS sob o grupo 'crio'
mkdir -p /etc/crio/crio.conf.d
cat <<EOF > /etc/crio/crio.conf.d/15-crio-socket.conf
[crio]
# Altera o grupo padrão do socket para que usuários no grupo 'crio' consigam acessá-lo sem sudo para chamadas puras
stream_share_group = "crio"
EOF
echo "Configuração do socket do CRI-O finalizada."

# ---------------------------------------------------------
echo ">>> 5.6. Executando testes de sanidade e compatibilidade..."
# ---------------------------------------------------------

# 1. Validar se o CRIU está instalado e funcional
if ! criu --version > /dev/null 2>&1; then
    echo "ERRO: CRIU não está instalado ou funcional!" >&2
    exit 1
fi

# 2. Validar se o checkpointctl está instalado e funcional
echo ">>> Verificando local do checkpointctl..."
which checkpointctl || true
echo ">>> Executando checkpointctl version..."
checkpointctl version || true
if ! command -v checkpointctl > /dev/null 2>&1; then
    echo "ERRO: checkpointctl não está instalado!" >&2
    exit 1
fi

# 3. Validar se o crun está instalado e possui suporte a CRIU (+CRIU)
if ! crun --version | grep -q "+CRIU"; then
    echo "ERRO: O runtime crun nativo não possui suporte a CRIU compilado!" >&2
    exit 1
fi

# 4. Validar se o link do runtime do CRI-O aponta para o crun correto
if [ "$(readlink -f /usr/libexec/crio/crun)" != "/usr/bin/crun" ]; then
    echo "ERRO: O runtime do CRI-O não está devidamente apontado para o crun nativo!" >&2
    exit 1
fi

echo ">>> Todos os testes de compatibilidade passaram com sucesso!"

# ---------------------------------------------------------
echo ">>> 6. Limpando cache do APT para diminuir o tamanho da imagem..."
# ---------------------------------------------------------
apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "========================================="
echo " Setup finalizado com sucesso!"
echo "========================================="
