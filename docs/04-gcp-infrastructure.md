# Infraestrutura GCP - Terraform e Packer

Este documento detalha o setup da infraestrutura em nuvem (Google Cloud Platform) do cluster de migração, cobrindo o provisionamento via Terraform e a criação de imagens customizadas Debian 13 otimizadas para CRI-O e CRIU com Packer.

---

## 🌐 1. Topologia de Rede e Recursos (Terraform)

Toda a infraestrutura é provisionada utilizando a pasta [google-cloud/compute](file:///home/matheus/Documents/master-usp/migration/google-cloud/compute). O Terraform define os seguintes recursos:

* **VPC Network (`vpc-network`)**: Rede privada isolada de baixa latência para comunicação entre os nós de migração.
* **Firewall Rules**:
  * Liberação de SSH externo para permitir acesso administrativo às VMs.
  * Liberação de tráfego interno ilimitado dentro da subnet da VPC para facilitar o gRPC, rsync, CNI e comunicação do Headscale.
* **Service Account (`simple-compute-engine`)**: Identidade anexada às VMs com as permissões:
  * `roles/storage.objectAdmin` (acesso aos buckets de armazenamento).
  * `roles/compute.admin` (gerenciamento das VMs).
  * `roles/iam.serviceAccountUser` (gerenciamento de privilégios de execução).
* **Virtual Machines**:
  * **Controller VM (Nó Coordenador)**: Instanciada a partir de uma imagem de controle customizada. Roda o daemon do orquestrador gRPC.
  * **Worker VMs (Nós de Execução)**: Instanciadas a partir da imagem customizada de execução do CRI-O/CRIU. Hospedam os contêineres a serem migrados.

### Provisionamento Automático
O Terraform utiliza o recurso `terraform_data` (`install_controller`) para automatizar as tarefas pós-inicialização da VM Coordenadora:
1. Copia a chave privada SSH local (`secrets`) e a estrutura de código (`python`, `files`) para a pasta `/home/dev/` da VM do Controlador.
2. Gera dinamicamente o arquivo [hosts.txt](file:///home/matheus/Documents/master-usp/migration/python/hosts.txt) contendo o IP interno de todas as instâncias ativas do cluster.
3. Roda o script de instalação automatizada [install.sh](file:///home/matheus/Documents/master-usp/migration/python/scripts/install.sh).

---

## 💿 2. Imagens Customizadas (Packer)

A geração das imagens virtuais é controlada pelos arquivos em [google-cloud/image](file:///home/matheus/Documents/master-usp/migration/google-cloud/image). 

### Debian Trixie (13) como Base
Usamos o Debian 13 como sistema operacional base devido ao suporte a pacotes mais atualizados do ecossistema de contêineres nos repositórios oficiais (CRIU v4.1.1 e crun v1.21).

### Setup Script (`scripts/setup.sh`)
O script realiza a preparação de baixo nível do sistema operacional para suportar o checkpoint iterativo:

1. **Módulos do Kernel & Sysctl**:
   * Carrega `overlay` e `br_netfilter`.
   * Habilita encaminhamento IPv4 (`net.ipv4.ip_forward = 1`) e hooks do iptables para bridges (`net.bridge.bridge-nf-call-iptables = 1`).
2. **CRIU & checkpointctl**:
   * Instala a versão nativa do sistema (`criu`, `libcriu2`, `libcriu-dev` e `checkpointctl`) para evitar conflito de RPATH do Nix.
3. **CRI-O Runtime**:
   * Configura o repositório oficial openSUSE da versão do CRI-O correspondente.
   * Instala o daemon `cri-o`, `containernetworking-plugins`, `runc` e `conmon`.
4. **Resolução dos Conflitos Críticos**:
   * **Nix/Glibc Mismatch**: Substitui o executável Nix do crun por um link simbólico para o crun nativo do Debian `/usr/bin/crun`, que possui o recurso `+CRIU` compilado.
   * **Bloqueios do AppArmor**: Desabilita perfis do AppArmor do `crun` e do `runc` que barram o envio de sinais de auditoria emitidos pelo `CRIU` ao pausar e restaurar processos.
   * **Incompatibilidade do CNI**: Baixa e instala manualmente os plugins CNI estáveis e atualizados do repositório oficial do GitHub em `/opt/cni/bin` para evitar o erro `MAC doesn't match` observado em pacotes legados do Debian.
5. **Criação de Usuário de Desenvolvimento (`dev`)**:
   * Cria o usuário `dev` com shell Bash.
   * Garante acesso administrativo adicionando-o ao grupo `sudo` e configurando privilégios sem senha (`NOPASSWD`).
   * Configura o socket UDS do CRI-O (`/var/run/crio/crio.sock`) sob o grupo de compartilhamento `crio` (`stream_share_group = "crio"`) e adiciona o usuário `dev` a este grupo.

---

## 🛠️ 3. Comandos de Manutenção da Infraestrutura

### Executando a Build do Packer
Para gerar novas imagens customizadas do cluster após alterar scripts de setup:
```bash
cd google-cloud/image
# Inicializa plugins do Packer
packer init .
# Constrói a imagem passando o arquivo de variáveis do GCP
packer build -var-file=env.pkrvars.hcl .
```

### Aplicando Alterações com o Terraform
Para subir a rede e criar as instâncias associando as novas imagens customizadas geradas:
```bash
cd google-cloud/compute
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```
*(As VMs serão inicializadas e o orquestrador configurado automaticamente no nó controlador).*
