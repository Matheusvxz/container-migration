# Plano de Melhorias do Orquestrador de Migração

Este documento propõe três melhorias para otimizar o desenvolvimento, depuração e desempenho da migração de contêineres no ambiente real.

---

## 🔄 1. Atualização Simplificada do Código do Controlador

### O Problema Atual
Atualmente, para atualizar o código do controlador (daemon e CLI), o processo exige limpar manualmente as pastas no servidor remoto ou forçar o Terraform a destruir e recriar o provisionamento (usando `-replace` no recurso `terraform_data.install_controller`). Isso é demorado e propenso a erros de caminhos aninhados.

### Proposta de Solução: Atualização Direta via Git ou Script Local

#### Opção A: Atualização Baseada em Repositório Git (Recomendado)
Configurar a pasta `/opt/migration-orchestrator` no controlador para ser um clone direto do repositório Git. 
Dessa forma, a atualização do código pode ser feita em segundos com uma chamada na CLI ou daemon:

1. Adicionar um comando `migration-cli update` que envia uma chamada gRPC para o Daemon.
2. O Daemon executa o seguinte script remoto:
   ```bash
   cd /opt/migration-orchestrator
   git pull origin main
   .venv/bin/pip install -e .
   sudo systemctl restart migration-daemon
   ```

#### Opção B: Script de Sincronização Local (Rsync Rápido)
Criar um script local (`scripts/deploy-controller.sh`) que sincroniza diretamente a pasta `python` local para a VM via `rsync` usando o IP do controller e a chave SSH:
```bash
#!/bin/bash
CONTROLLER_IP=$(cd google-cloud/compute && terraform output -json controller_details | jq -r '.["host-1"].external_ip')
rsync -avz --exclude='.venv' --exclude='__pycache__' ./python/ dev@$CONTROLLER_IP:/home/dev/python/
ssh -i secrets/key dev@$CONTROLLER_IP "sudo bash /home/dev/python/scripts/install.sh"
```
Isso elimina a necessidade de interações com o estado do Terraform para atualizações rápidas de código.

---

## 💻 2. Execução Direta de Comandos `crictl` via CLI / gRPC

### O Problema Atual
Durante testes e depurações, é frequente precisar inspecionar o estado dos contêineres nos nós A e B (ex: `crictl ps`, `crictl images`, `crictl inspect`). Fazer isso manualmente exige abrir novas sessões SSH para cada nó, o que atrasa a verificação.

### Proposta de Solução: Encapsulamento de Comandos `crictl` no Orquestrador

1. **Protocolo gRPC (`migration.proto`)**:
   Adicionar uma nova chamada de procedimento remoto (RPC):
   ```proto
   rpc ExecuteCrictl(CrictlRequest) returns (CrictlResponse);

   message CrictlRequest {
     string node_ip = 1;
     string command = 2; // ex: "ps -a", "images", "inspect <id>"
   }

   message CrictlResponse {
     string stdout = 1;
     string stderr = 2;
     int32 exit_code = 3;
   }
   ```

2. **Daemon (`daemon.py` / `migration.py`)**:
   O daemon recebe o IP do nó e o comando `crictl`. Ele localiza a conexão SSH ativa para aquele nó (`self.connections.get(node_ip)`) e executa:
   ```python
   result = await conn.run(f"sudo crictl {command}")
   ```
   Em seguida, retorna a saída padrão, saída de erro e o código de saída.

3. **Interface de Linha de Comando (CLI)**:
   Disponibilizar o comando na CLI do controlador:
   ```bash
   migration-cli node-exec --node <IP_DO_NO> -- <comando_crictl>
   # Exemplo de uso:
   migration-cli node-exec --node 10.128.0.10 ps -a
   migration-cli node-exec --node 10.128.0.8 images
   ```

---

## 📦 3. Compactação de Checkpoints e Pre-Dumps antes da Transferência

### O Problema Atual
Atualmente, as pastas do pre-dump (ex: `/tmp/iter1_<job_id>`) são copiadas diretamente via `rsync` arquivo por arquivo. Os arquivos de checkpoint de memória (como `pages-1.img`) tendem a ser grandes e contêm alta redundância. Transferir arquivos grandes sem compressão aumenta o consumo de banda de rede e o tempo total de migração, elevando o downtime.

### Proposta de Solução: Empacotamento Compactado na Origem

Em vez de enviar os arquivos em seu estado bruto via rsync de diretório, podemos compactar o dump localmente e depois descompactar no destino.

1. **Compactação na Origem (Nó A)**:
   Antes de chamar a transferência, a classe `StorageManager` ou o fluxo em `migration.py` executa uma compactação rápida (utilizando `gzip` ou `zstd` para alto desempenho):
   ```bash
   tar -czf /tmp/iter1_job.tar.gz -C /tmp/iter1_job .
   ```
   
2. **Transferência de Arquivo Único**:
   O `rsync` transfere apenas o arquivo `/tmp/iter1_job.tar.gz`. Como é um único arquivo compactado, a velocidade de transferência melhora significativamente.
   
3. **Descompactação no Destino (Nó B)**:
   Ao receber o arquivo, o nó de destino executa a extração:
   ```bash
   mkdir -p /tmp/iter1_job
   tar -xzf /tmp/iter1_job.tar.gz -C /tmp/iter1_job
   rm -f /tmp/iter1_job.tar.gz
   ```

4. **Benefício Esperado**:
   * Redução de até **70-80%** nos dados transmitidos na rede (dependendo do footprint de memória do contêiner).
   * Redução correspondente no tempo da etapa `TRANSFERRING_FINAL_DUMP` no momento do congelamento, reduzindo drasticamente o downtime percebido.
