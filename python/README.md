# Orquestrador Assíncrono de Migração de Contêineres (Arquitetura CLI + Daemon gRPC)

Este projeto implementa uma arquitetura robusta de controle dividida em duas partes principais:
1. **Daemon gRPC (Orquestrador/Serviço)**: Executado como um serviço de sistema (background daemon) no nó coordenador. Ele gerencia o pool de conexões SSH assíncronas para os hosts do cluster, realiza varreduras em background, mantém o controle de jobs e orquestra as migrações concorrentes sem bloqueios.
2. **CLI de Controle (`migration-cli`)**: Uma ferramenta de linha de comando super leve que se conecta via gRPC ao Daemon para interagir com o cluster, monitorar o status e disparar novas migrações.

A comunicação ocorre de forma performática via **gRPC** utilizando stubs compilados a partir da especificação [migration.proto](file:///home/matheus/Documents/master-usp/migration/python/migration.proto).

---

## Estrutura do Código (`python/`)

Toda a lógica está organizada seguindo padrões modernos do ecossistema Python (layout `src/` e empacotamento declarativo via [pyproject.toml](file:///home/matheus/Documents/master-usp/migration/python/pyproject.toml)):

- [proto/migration.proto](file:///home/matheus/Documents/master-usp/migration/python/proto/migration.proto): Especificação de protocolo do gRPC (contrato de APIs).
- [scripts/compile_proto.py](file:///home/matheus/Documents/master-usp/migration/python/scripts/compile_proto.py): Script utilitário para compilar o arquivo `.proto` em stubs Python direcionados para o pacote de proto interno.
- [scripts/install.sh](file:///home/matheus/Documents/master-usp/migration/python/scripts/install.sh): Script shell automatizado para deploy total do daemon como serviço de sistema (`systemd`), empacotamento pelo pip no ambiente virtual e atalho global da CLI.
- [scripts/migration-daemon.service](file:///home/matheus/Documents/master-usp/migration/python/scripts/migration-daemon.service): Arquivo de configuração de serviço systemd para o Daemon.
- [hosts.txt](file:///home/matheus/Documents/master-usp/migration/python/hosts.txt): Arquivo de configuração para listar os IPs das VMs do cluster.
- **`src/orchestrator/`**: Pacote principal Python:
  - [src/orchestrator/cli.py](file:///home/matheus/Documents/master-usp/migration/python/src/orchestrator/cli.py): CLI gRPC de controle e monitoramento do cluster.
  - [src/orchestrator/daemon.py](file:///home/matheus/Documents/master-usp/migration/python/src/orchestrator/daemon.py): O servidor gRPC assíncrono que expõe o `MigrationManager`.
  - [src/orchestrator/models.py](file:///home/matheus/Documents/master-usp/migration/python/src/orchestrator/models.py): Modelagem de dados comum (Nodes, Containers, Jobs).
  - **`core/`**: Regras de negócio de alto nível:
    - [src/orchestrator/core/migration.py](file:///home/matheus/Documents/master-usp/migration/python/src/orchestrator/core/migration.py): O orquestrador assíncrono central (`asyncio`).
    - [src/orchestrator/core/storage.py](file:///home/matheus/Documents/master-usp/migration/python/src/orchestrator/core/storage.py): Manipula a extração, links e transferência direta de checkpoints via `rsync`.
  - **`drivers/`**: Integrações de baixo nível:
    - [src/orchestrator/drivers/cri.py](file:///home/matheus/Documents/master-usp/migration/python/src/orchestrator/drivers/cri.py): Interface com o CRI-O via CLI `crictl`.
    - [src/orchestrator/drivers/runc.py](file:///home/matheus/Documents/master-usp/migration/python/src/orchestrator/drivers/runc.py): Executa checkpoints incrementais e finais via runc.

---

## Como Instalar na VM do Coordenador

Criamos um script de instalação completo que automatiza o deploy no diretório padrão `/opt/migration-orchestrator`, cria um ambiente virtual (venv), instala os pacotes como um pacote de sistema (via `pyproject.toml`), compila o protobuf, configura o serviço `systemd` (`migration-daemon`) e registra o atalho CLI `/usr/local/bin/migration-cli`.

### Passo 1: Configurar a Lista de IPs dos Nós
Antes de rodar o instalador, configure os IPs das suas VMs editando o arquivo [hosts.txt](file:///home/matheus/Documents/master-usp/migration/python/hosts.txt) local.

### Passo 2: Executar o Instalador
Execute o script `install.sh` com permissões de execução (ele solicitará privilégios `sudo` apenas para configurar o systemd e registrar a CLI global):

```bash
# Permite execução do instalador
chmod +x python/scripts/install.sh

# Roda a instalação
./python/scripts/install.sh
```

---

## Como Utilizar a CLI Global (`migration-cli`)

Após a instalação, o comando `migration-cli` estará disponível globalmente no seu terminal para qualquer usuário logado.

### 1. Listar o Estado do Cluster (Varredura em Tempo Real)
Obtém o status de conexão de cada nó configurado no `/opt/migration-orchestrator/hosts.txt` e lista todos os pods e contêineres ativamente rodando:

```bash
migration-cli list
```

### 2. Disparar uma Nova Migração Iterativa Incremental
Dispara a migração concorrente de forma assíncrona. O Daemon assume o fluxo em paralelo em background e retorna o ID do Job para acompanhamento. A flag `--watch` permite monitorar o passo a passo até a finalização:

```bash
migration-cli migrate --container <ID_CONTAINER> --source <IP_ORIGEM> --target <IP_DESTINO> --pre-dumps 2 --watch
```

### 3. Executar Migração Interativa Passo-a-Passo

A migração interativa permite executar múltiplos pre-dumps de memória sob demanda e enviá-los ao destino enquanto o contêiner continua ativo na origem. Isso oferece controle manual e redução extrema de downtime no passo final.

#### Passo A: Inicializar a sessão de migração interativa
```bash
migration-cli migrate-interactive start --container <ID_CONTAINER> --source <IP_ORIGEM> --target <IP_DESTINO>
```
Este comando exportará os metadados iniciais e retornará um `UUID_DO_JOB` que deve ser mantido para os próximos passos.

#### Passo B: Gerar pre-dumps incrementais (execute quantas vezes desejar)
```bash
# Gera o pre-dump na origem mas mantém localmente
migration-cli migrate-interactive pre-dump --job <UUID_DO_JOB>

# Gera o pre-dump e o envia imediatamente ao destino via rsync (Recomendado para otimizar downtime)
migration-cli migrate-interactive pre-dump --job <UUID_DO_JOB> --transfer
```

#### Passo C: Executar o checkpoint final, transferir e restaurar
```bash
migration-cli migrate-interactive final --job <UUID_DO_JOB>
```
Este comando sincroniza automaticamente qualquer pre-dump que tenha sido gerado sem a flag `--transfer`, realiza o checkpoint final na origem parando o contêiner, transfere o dump final, consolida o tarball diretamente no destino e conclui a restauração do serviço no novo host (acompanhando o progresso em tempo real).

### 4. Visualizar Status e Jobs Ativos no Daemon
Consulta todos os processos de migração registrados no Daemon:

```bash
# Ver lista de todos os jobs
migration-cli jobs

# Consultar status detalhado de um job específico
migration-cli status --job <UUID_DO_JOB>
```

### 4. Forçar Atualização de Dados (Scan Remoto)
Força o Daemon a realizar uma varredura imediata via gRPC/CRI nos nós em execução para atualizar os status:

```bash
migration-cli refresh
```

### 5. Gerenciamento Dinâmico de Hosts (Nós)
Você pode gerenciar os nós de execução ativamente em tempo de execução via CLI. O daemon atualizará as conexões SSH em memória, iniciará a varredura automática dos contêineres neles e persistirá as alterações de volta no arquivo de hosts configurado:

```bash
# Adicionar um novo host
migration-cli add 10.128.0.4

# Remover um host monitorado e encerrar a sua conexão SSH de forma limpa
migration-cli remove 10.128.0.2

# Sobrescrever toda a lista de hosts monitorados de uma vez
migration-cli set 10.128.0.10 10.128.0.11 10.128.0.12
```

---

## Controle do Serviço Daemon (`systemd`)

Como o daemon é gerenciado nativamente pelo `systemd`, você pode monitorar logs ou controlar seu status usando comandos de sistema normais:

```bash
# Ver status do serviço
sudo systemctl status migration-daemon

# Monitorar logs do Daemon em tempo real (journalctl)
sudo journalctl -u migration-daemon -f

# Reiniciar o daemon (caso edite o /opt/migration-orchestrator/hosts.txt)
sudo systemctl restart migration-daemon
```
