# Guia de Validação em Ambiente Real - Migração Interativa

Este guia descreve os passos necessários para realizar a validação completa de ponta a ponta da migração interativa de contêineres em um laboratório real contendo **1 VM Controladora** e **2 VMs de Execução (Nós A e B)**.

---

## 🏗️ 1. Cenário e Pré-requisitos

### Topologia das VMs:
1. **Controladora (Coordinator)**: Onde reside o daemon gRPC e a CLI do orquestrador.
2. **Nó A (Origem - IP `IP_NO_A`)**: Onde o contêiner iniciará rodando.
3. **Nó B (Destino - IP `IP_NO_B`)**: Para onde o contêiner será migrado.

### Pré-requisitos nas Máquinas:
- A controladora possui a chave privada SSH correspondente (ex: em `python/secrets/key`) com acesso root/sudo sem senha (`dev` ou usuário configurado) aos nós A e B.
- Os nós A e B possuem `CRI-O`, `crictl` e `runc` instalados e configurados para suportar checkpoint/restore (CRIU).
- O daemon gRPC está em execução na controladora.

---

## 🚀 2. Preparação do Ambiente

### Passo 2.1: Registrar os Nós no Orquestrador
Na Controladora, defina a lista de hosts ativos utilizando a CLI:
```bash
migration-cli set <IP_NO_A> <IP_NO_B>
```
Valide se as conexões foram estabelecidas com sucesso rodando:
```bash
migration-cli list
```
*(Espera-se ver ambos os hosts com status `ONLINE`)*

### Passo 2.2: Inicializar o Contêiner de Teste no Nó A
Inicialize um contêiner de teste (por exemplo, Redis) no Nó A a partir da controladora:
```bash
migration-cli run --node <IP_NO_A> --pod-config /home/dev/files/pod-localhost.json --container-config /home/dev/files/container-redis.json
```
Verifique se o contêiner está ativo rodando:
```bash
migration-cli list
```
*(Espera-se ver o contêiner listado sob o `IP_NO_A` com estado `RUNNING`)*

---

## 🔄 3. Execução da Migração Interativa

### Passo 3.1: Inicializar a Migração (Start)
Inicie a migração interativa informando o ID do contêiner obtido no passo anterior:
```bash
migration-cli migrate-interactive start --container <CONTAINER_ID> --source <IP_NO_A> --target <IP_NO_B>
```
#### Itens a validar após a execução:
- [ ] A CLI retorna uma mensagem de sucesso exibindo o `ID do Job de Migração` (salve este UUID).
- [ ] **No Nó A**: Verifique se o arquivo `/tmp/dummy-checkpoint_<UUID_DO_JOB>.tar` foi criado.
- [ ] O contêiner no Nó A continua no estado `RUNNING` e respondendo normalmente.

---

### Passo 3.2: Geração de Pre-Dumps Incrementais

#### Teste 1: Pre-dump com Transferência Imediata
Gere a primeira iteração incremental e solicite a cópia imediata para o destino:
```bash
migration-cli migrate-interactive pre-dump --job <UUID_DO_JOB> --transfer
```
#### Itens a validar após a execução:
- [ ] A CLI responde com sucesso indicando `Iteração: 1` e `Transferido: Sim`.
- [ ] **No Nó A**: A pasta `/tmp/iter1_<UUID_DO_JOB>` foi criada e contém os arquivos de dump da memória.
- [ ] **No Nó B**: Verifique se a pasta `/tmp/iter1_<UUID_DO_JOB>` foi copiada e existe de forma idêntica.
- [ ] O contêiner no Nó A permanece `RUNNING`.

#### Teste 2: Pre-dump sem Transferência Imediata (para validar sincronização automática)
Gere uma segunda iteração incremental, mas opte por mantê-la apenas localmente na origem:
```bash
migration-cli migrate-interactive pre-dump --job <UUID_DO_JOB>
```
#### Itens a validar após a execução:
- [ ] A CLI responde com sucesso indicando `Iteração: 2` e `Transferido: Não`.
- [ ] **No Nó A**: A pasta `/tmp/iter2_<UUID_DO_JOB>` foi criada com os deltas mais recentes da memória.
- [ ] **No Nó B**: A pasta `/tmp/iter2_<UUID_DO_JOB>` **não** deve estar presente no destino neste momento.
- [ ] O contêiner no Nó A permanece `RUNNING`.

---

### Passo 3.3: Finalização da Migração (Final)
Execute o comando final para congelar o contêiner original e restaurar no destino:
```bash
migration-cli migrate-interactive final --job <UUID_DO_JOB>
```

#### Acompanhamento em tempo real das etapas na CLI:
1. `SYNCING_UNTRANSFERRED_DRAINS`: O orquestrador detecta que a iteração 2 não foi enviada anteriormente e a transfere automaticamente para o Nó B.
   - *Validação intermediária*: A pasta `/tmp/iter2_<UUID_DO_JOB>` agora existe no Nó B.
2. `FINAL_CHECKPOINT`: O contêiner original no Nó A é congelado e parado pelo runc.
   - *Validação intermediária*: O contêiner no Nó A deixa de responder e entra em estado de parada.
3. `TRANSFERRING_FINAL_DUMP`: Transfere a iteração final de parada `/tmp/iter_final_<UUID_DO_JOB>` e os metadados `/tmp/dummy-checkpoint_<UUID_DO_JOB>.tar` para o Nó B.
4. `PREPARING_TARBALL`: Executa o empacotamento em tarball consolidando as iterações 1, 2 e final diretamente **dentro do Nó B**.
5. `RESTORING`: Cria o Pod Sandbox, registra o contêiner a partir do tarball e restaura a memória no Nó B.
6. `CLEANING_SOURCE` / `FINALIZING`: Remove o contêiner antigo no Nó A e deleta todos os lixos temporários em `/tmp/` no Nó A e Nó B.

---

## 🏆 4. Verificação de Sucesso

Após a conclusão da migração pelo comando final:

1. **Validação do Estado Global**:
   ```bash
   migration-cli list
   ```
   - O contêiner não deve mais constar sob o `IP_NO_A`.
   - O contêiner deve constar no `IP_NO_B` com o estado `RUNNING`.

2. **Validação de Limpeza (Cleanup)**:
   - **No Nó A**: Os arquivos temporários `/tmp/*_<UUID_DO_JOB>*` foram removidos.
   - **No Nó B**: Os arquivos temporários `/tmp/*_<UUID_DO_JOB>*` e o tarball `/tmp/redis-checkpoint.tar` foram removidos.

3. **Verificação de Downtime**:
   - Os logs do daemon (`journalctl -u migration-daemon -f`) exibirão o tempo de duração da etapa `final`. Esse valor deve ser substancialmente menor em comparação com uma migração não-interativa tradicional, demonstrando a eficácia do pré-estagiamento das páginas de memória.
