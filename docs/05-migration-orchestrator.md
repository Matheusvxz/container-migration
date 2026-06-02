# Orquestrador de Migração - CLI e Daemon gRPC (Python)

Este documento descreve a arquitetura de software, fluxo de execução assíncrono e implementação técnica do Orquestrador de Migração desenvolvido em Python, localizado em [python/](file:///home/matheus/Documents/master-usp/migration/python).

---

## 🏗️ 1. Arquitetura Geral

O orquestrador é baseado em uma arquitetura Cliente-Servidor distribuída de controle:

* **Daemon (`daemon.py`)**: Roda em background no Nó Coordenador como um serviço de sistema (`systemd`). Escuta conexões gRPC, monitora o estado de conexões SSH ativas e coordena os Jobs de migração de forma concorrente sem travamentos.
* **CLI (`cli.py`)**: Interface de terminal leve para os administradores do sistema. Conecta-se via gRPC ao Daemon e executa comandos como `list`, `migrate`, `jobs`, `status`, `refresh`, `add`, `remove` e `set`.
* **gRPC Contract (`migration.proto`)**: O contrato define as chamadas e mensagens para consulta de inventário do cluster, criação de jobs de migração, streams de status em tempo real e comandos de atualização.

---

## 🔄 2. Máquina de Estados e Fluxo Assíncrono (`asyncio`)

O daemon usa a biblioteca `asyncio` e conexões SSH persistentes assíncronas através do `asyncssh` para controlar as VMs de forma paralela.

### O Fluxo Completo de Migração (`MigrationManager._execute_migration_workflow`)

Quando uma migração é disparada, o Daemon a executa em uma Task separada em background. O ciclo de vida do Job segue os seguintes passos estruturados:

```
[PENDING] -> [INITIALIZING] -> [EXPORTING_METADATA] -> [PRE_DUMPING] -> 
  [FINAL_CHECKPOINT] -> [PREPARING_TARBALL] -> [TRANSFERRING] -> 
  [PREPARING_TARGET_CONFIGS] -> [RESTORING] -> [CLEANING_SOURCE] -> [FINALIZING] -> [COMPLETED]
```

#### Passo 1: Exportação de Metadados (`EXPORTING_METADATA`)
Invoca `crictl checkpoint` com o argumento `--export` para gerar um arquivo temporário contendo a especificação OCI do contêiner, montagens de volume e configurações de segurança:
* Binário utilitário: [cri_client.py](file:///home/matheus/Documents/master-usp/migration/python/cri_client.py)
* Destino: `/tmp/dummy-checkpoint_<job_id>.tar`

#### Passo 2: Checkpoints Iterativos Incrementais (`PRE_DUMPING`)
Utiliza o `RuncClient` em [runc_client.py](file:///home/matheus/Documents/master-usp/migration/python/runc_client.py) para realizar múltiplos pre-dumps de memória com o contêiner ainda rodando:
* **Primeira Iteração (Pre-dump inicial)**:
  `runc --root /run/runc checkpoint --pre-dump --image-path /tmp/iter1_<job_id> <CONTAINER_ID>`
* **Iterações Subsequentes**:
  Passa o parâmetro `--parent-path` apontando de forma relativa para a pasta da iteração anterior.
  `runc --root /run/runc checkpoint --pre-dump --parent-path ../iter1_<job_id> --image-path /tmp/iter2_<job_id> <CONTAINER_ID>`

#### Passo 3: Checkpoint Final de Parada (`FINAL_CHECKPOINT`)
Captura as últimas páginas de memória modificadas (dirty pages) e para o contêiner de origem imediatamente, minimizando o downtime de serviço:
`runc --root /run/runc checkpoint --parent-path ../iterN_<job_id> --image-path /tmp/iter_final_<job_id> <CONTAINER_ID>`

#### Passo 4: Consolidação do Tarball Autocontido (`PREPARING_TARBALL`)
O CRI-O extrai e restaura o tarball dentro de namespaces privados isolados (`/run/containers/.../userdata/`). Se os metadados do checkpoint apontarem para caminhos absolutos do host (como `/tmp/iter1`), a restauração falhará por falta de visibilidade.
Para resolver isso, o [storage_manager.py](file:///home/matheus/Documents/master-usp/migration/python/storage_manager.py) monta uma estrutura autocontida dentro de um diretório privado `/tmp/restore_tar_<job_id>`:
1. Extrai o `dummy-checkpoint.tar` temporário.
2. Remove o diretório de memória padrão `/checkpoint` e o substitui pela pasta final do checkpoint de parada (`iter_final`).
3. Copia todas as pastas incrementais (`iter1`, `iter2`, etc.) para dentro da mesma raiz.
4. **Resolução de Parentesco Relativo**: Sobrescreve os links simbólicos de memória `parent` para usarem caminhos relativos internos apontando para a estrutura empacotada:
   * `/checkpoint/parent` -> `../iterN_<job_id>`
   * `/iterN_<job_id>/parent` -> `../iterN-1_<job_id>`
5. Compacta tudo em `/tmp/redis-checkpoint_<job_id>.tar`.

#### Passo 5: Transferência Inteligente (`TRANSFERRING`)
Transfere o tarball empacotado para o IP de destino via `rsync` de forma otimizada.
* **Segurança da Chave**: O `StorageManager` grava a chave SSH privada temporariamente em `/tmp/migration_transfer_key` no nó de origem, executa a transferência via túnel rsync sem validação de host e limpa a chave da origem no bloco `finally`.

#### Passo 6: Criação e Restauração no Destino (`RESTORING`)
No nó de destino:
1. Sobe o pod sandbox via crictl (`crictl runp`).
2. Instancia o contêiner referenciando o tarball recebido como a imagem (`crictl create`).
3. Executa a restauração da memória (`crictl start`).

#### Passo 7: Limpeza de Recursos (`CLEANING_SOURCE` & `FINALIZING`)
* Destrói o pod e contêiner antigos no nó de origem.
* Limpa todos os logs de memória e tarballs temporários gerados em ambas as máquinas para preservar espaço em disco.

### 🔄 3. Fluxo de Migração Interativa Passo-a-Passo

Para cenários onde o administrador deseja controlar o tempo exato de geração dos pre-dumps e de transferência da memória para o nó de destino de forma manual/interativa, o orquestrador fornece os subcomandos de `migrate-interactive`.

Esse fluxo funciona de forma desacoplada através dos seguintes comandos síncronos na CLI:

1. **Inicialização (`start`)**:
   `migration-cli migrate-interactive start --container <ID> --source <IP_A> --target <IP_B> [--pod-config <caminho>] [--container-config <caminho>]`
   * Valida as conexões SSH nos hosts de origem e destino.
   * Cria o Job persistente em memória no Daemon gRPC.
   * Executa a exportação de metadados inicial (`crictl checkpoint`) gerando `/tmp/dummy-checkpoint_<job_id>.tar` no nó de origem.
   * Retorna o UUID do Job para acompanhamento das próximas fases.

2. **Geração Incremental (`pre-dump`)**:
   `migration-cli migrate-interactive pre-dump --job <UUID> [--transfer]`
   * Pode ser executado múltiplas vezes de forma incremental com o contêiner rodando.
   * Executa `runc checkpoint --pre-dump` no nó de origem mantendo o contêiner ativo.
   * O parâmetro `--parent-path` é configurado automaticamente apontando de forma relativa para a iteração anterior.
   * Se a flag `--transfer` for passada, a pasta `iterX` correspondente é copiada imediatamente para o nó de destino via `rsync`. Isso permite que o tráfego pesado de memória ocorra com o serviço no ar.

3. **Finalização e Restauração (`final`)**:
   `migration-cli migrate-interactive final --job <UUID>`
   * O comando verifica se existem pre-dumps gerados na origem que ainda não foram transferidos e os copia automaticamente para o destino.
   * Para o contêiner na origem e realiza o checkpoint de parada final (`final_checkpoint`).
   * Transfere o dump final e os metadados para o destino.
   * **Consolidação no Destino**: Ao contrário do fluxo padrão, a consolidação (criação do tarball completo via `prepare_tarball`) é executada **diretamente no nó de destino B**. Isso reduz drasticamente o downtime do serviço, já que as iterações anteriores de memória já residem no destino.
   * Restaura o Pod e Contêiner no nó de destino B e realiza o cleanup dos recursos temporários e do contêiner original na origem.

---

## ⚙️ 3. Deploy Automático e Gerenciamento

O projeto inclui o script [install.sh](file:///home/matheus/Documents/master-usp/migration/python/scripts/install.sh) para deploy total:

```bash
# Executado internamente pelo Terraform no boot do Coordenador
./python/scripts/install.sh
```

Ações executadas pelo instalador:
1. Cria a pasta da aplicação `/opt/migration-orchestrator`.
2. Inicializa um ambiente virtual Python (`venv`) e instala as dependências e o projeto como um pacote via [pyproject.toml](file:///home/matheus/Documents/master-usp/migration/python/pyproject.toml).
3. Compila a especificação [migration.proto](file:///home/matheus/Documents/master-usp/migration/python/proto/migration.proto) para stubs do Python via `compile_proto.py` direcionando-os para `orchestrator/proto/`.
4. Registra o serviço do Daemon no systemd copiado de [migration-daemon.service](file:///home/matheus/Documents/master-usp/migration/python/scripts/migration-daemon.service).
5. Cria um link simbólico para a CLI global em `/usr/local/bin/migration-cli`.

### Comandos Úteis do Daemon

```bash
# Monitorar o log de migração em tempo real
sudo journalctl -u migration-daemon -f

# Reiniciar o serviço
sudo systemctl restart migration-daemon
```

### 🔧 4. Gerenciamento Dinâmico de Hosts
Com a atualização do protocolo gRPC e do Core do `MigrationManager`, agora é possível inserir, remover ou substituir os nós sob monitoramento em tempo real:
* **Fluxo**: Ao rodar um comando como `migration-cli add 10.128.0.4`, o Daemon estabelece conexões SSH assíncronas assincronamente via `asyncssh`, executa varredura de contêineres e registra a alteração persistindo o novo conteúdo no arquivo `/opt/migration-orchestrator/hosts.txt`.
* **Benefício**: Evita downtime no serviço do Daemon gRPC e reinicializações desnecessárias de sistema apenas para atualizar o inventário físico de computadores do cluster.

