# GCP Custom Image Manager - CLI Interativa (TypeScript)

Este documento descreve o funcionamento, design e instruções de execução da ferramenta de CLI interativa desenvolvida em Node.js e TypeScript para gerenciamento de imagens customizadas no Google Cloud Platform, localizada na raiz do projeto (`package.json`, `src/cli.ts`).

---

## 💡 1. Objetivo da Ferramenta

Durante o desenvolvimento do ambiente do cluster (Packer builds e testes), muitas imagens customizadas antigas e desatualizadas do Debian são criadas no GCP. Para evitar custos adicionais de armazenamento na nuvem e poluição visual de recursos, a ferramenta `gcp-image-manager-cli` fornece uma interface de terminal (TUI) interativa e amigável para listar e deletar essas imagens em lote.

---

## 🛠️ 2. Arquitetura e Tecnologias

A CLI é construída com as seguintes tecnologias de desenvolvimento moderno:

* **Node.js (Módulo ESM)**: Executável JavaScript moderno rodando direto na máquina.
* **TypeScript & tsx**: Tipagem estática compilada de forma transparente e execução em tempo de desenvolvimento via `tsx` (TypeScript Execute).
* **`@clack/prompts`**: Engine visual de prompts interativos (seleção múltipla, loaders spinners, diálogos de texto e botões de confirmação).
* **`commander`**: Parser de argumentos de linha de comando para suportar flags adicionais.
* **`picocolors`**: Colorização ANSI premium do terminal para logs e realces de sucesso/erro.
* **`gcloud` Wrapper**: Executa sub-processos dinâmicos (`execSync`) conversando com o SDK local da Google Cloud CLI.

---

## ⚡ 3. Funcionalidades Principais

1. **Auto-Detecção do Projeto Ativo**:
   * O utilitário tenta executar `gcloud config get-value project` para identificar se o desenvolvedor já está logado em um projeto ativo.
   * Caso não haja projeto ativo configurado, a CLI abre um prompt interativo solicitando a digitação manual do ID do Projeto GCP.
2. **Varredura no GCP**:
   * Filtra e traz apenas imagens customizadas do usuário (`--no-standard-images`) no formato JSON estruturado.
   * Ordena as imagens por data de criação (mais recentes primeiro).
3. **Menu Interativo de Exclusão**:
   * Apresenta uma caixa de seleção múltipla com controle por teclado (setas para navegar, `Espaço` para marcar/desmarcar e `Enter` para confirmar).
   * Cada imagem mostra metadados úteis: Tamanho em disco (GB), Família associada, Data detalhada de criação e Status.
4. **Modo de Simulação (`--dry-run`)**:
   * Permite testar o fluxo de exclusão exibindo as imagens selecionadas sem disparar as exclusões reais contra as APIs do GCP.
5. **Logs de Sucesso e Progresso**:
   * Exibe mensagens de feedback individuais indicando o progresso da deleção em lote (ex: `[1/3] Deletando imagem... Sucesso!`).

---

## 🚀 4. Como Executar

### Pré-requisitos
* Node.js v18 ou superior instalado.
* `gcloud` SDK instalado, configurado e autenticado (`gcloud auth login`).

### Instalar Dependências
```bash
# Na raiz do repositório
npm install
```

### Executar a CLI
```bash
# Executa de forma interativa usando o projeto ativo detectado
npm start

# Executa forçando um projeto específico
npm start -- --project meu-projeto-gcp-123

# Executa em modo de simulação (Dry Run)
npm start -- --dry-run
```
*(Nota: O duplo traço `--` é necessário para passar argumentos através do script `npm run` para o processo `tsx`).*
