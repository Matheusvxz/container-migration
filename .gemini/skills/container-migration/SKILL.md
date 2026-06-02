---
name: container-migration
description: >-
  Consults the documentation base in docs/ to understand the current container migration and GCP infra state, ensuring documentation is kept up-to-date.
---

# Habilidade de Migração de Contêineres (Base de Conhecimento)

Esta habilidade orienta o agente de desenvolvimento de IA a alinhar-se com o estado do repositório, aplicar decisões de engenharia validadas e garantir que a documentação técnica seja mantida 100% atualizada a cada modificação realizada.

---

## 🔍 Fluxo de Alinhamento e Execução

### 1. Leitura Inicial (Startup)
Sempre que iniciar um novo chat ou tarefa neste repositório, o agente deve:
- Ler [docs/README.md](file:///home/matheus/Documents/master-usp/migration/docs/README.md) para obter o mapa de componentes.
- Consultar o documento do módulo correspondente à tarefa em execução:
  - Para alterações no cluster e VMs GCP: consulte [docs/04-gcp-infrastructure.md](file:///home/matheus/Documents/master-usp/migration/docs/04-gcp-infrastructure.md).
  - Para alterações no código do orquestrador Python: consulte [docs/05-migration-orchestrator.md](file:///home/matheus/Documents/master-usp/migration/docs/05-migration-orchestrator.md).
  - Para alterações na ferramenta GCP Image Manager CLI: consulte [docs/06-gcp-image-manager-cli.md](file:///home/matheus/Documents/master-usp/migration/docs/06-gcp-image-manager-cli.md).

### 2. Implementação com Padrões Consolidados
Ao modificar o código do projeto, siga estritamente os padrões validados:
- **CRIU / crun**: Sempre aponte o runtime do CRI-O para o executável dinâmico `/usr/bin/crun` do host Debian (e desabilite os perfis do AppArmor do `crun`/`runc` se ocorrerem bloqueios de permissão).
- **Metadados Incrementais (pre-dump)**: Ajuste os links simbólicos de parentesco (`parent`) de forma **relativa interna** (ex: `checkpoint/parent -> ../iter2`) para que o tarball seja auto-contido e portátil.
- **Rsync SSH**: A transferência de arquivos entre os nós deve utilizar chaves privadas efêmeras removidas de forma segura em blocos `finally`.

### 3. Atualização de Documentos
- Sempre que alterar código de scripts, arquivos de configuração ou infraestrutura, a documentação correspondente na pasta [docs/](file:///home/matheus/Documents/master-usp/migration/docs) **deve** ser atualizada antes de encerrar o chat.
- Se novas ferramentas ou componentes de infraestrutura forem criados, adicione novos arquivos na pasta `docs/` e mapeie-os no índice principal.
